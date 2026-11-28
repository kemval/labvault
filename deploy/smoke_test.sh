#!/bin/sh
# End-to-end test of the production image (roadmap 5.2, ADR 0024), with S3Mock
# standing in for S3. Proves that a database written in one container comes
# back, through Litestream, in a new container on an empty volume:
#
#   1. start LabVault (secure mode) with a replica; wait until healthy
#   2. write a marker audit entry; stop the container (Litestream's final sync)
#   3. delete the container AND its volume
#   4. start a new container on a new, empty volume: it must restore,
#      become healthy, contain the marker and pass the restore-drill check
#   5. started with LABVAULT_DEMO_MODE=true, the production image must refuse
#
#   deploy/smoke_test.sh [image]        # default labvault:dev
set -eu

IMAGE="${1:-labvault:dev}"
RUN="lv-smoke-$$"
NET="$RUN-net"
MARKER="smoke-$$-$(date +%s)"
ADMIN_PASSWORD="smoke-test-password-1"

cleanup() {
  docker rm -f "$RUN-s3" "$RUN-app" >/dev/null 2>&1 || true
  docker volume rm "$RUN-v1" "$RUN-v2" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

step() { printf '\n== %s\n' "$*"; }

start_app() {   # $1 = volume; further arguments go to docker run
  vol="$1"; shift
  docker run -d --name "$RUN-app" --network "$NET" -v "$vol:/data" "$@" \
    -e LABVAULT_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    -e LITESTREAM_REPLICA_URL="s3://labvault-smoke/prod" \
    -e LITESTREAM_S3_ENDPOINT="http://$RUN-s3:9090" \
    -e LITESTREAM_S3_REGION="us-east-1" \
    -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test \
    "$IMAGE" >/dev/null
}

wait_healthy() {
  for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$RUN-app" 2>/dev/null || echo gone)"
    [ "$status" = healthy ] && { echo "healthy"; return 0; }
    [ "$status" = gone ] && break
    sleep 2
  done
  echo "container did not become healthy (status: ${status:-unknown})" >&2
  docker logs "$RUN-app" >&2 || true
  return 1
}

in_app() {   # Python inside the container, without Streamlit's "No runtime found" noise
  status=0
  out="$(docker exec "$RUN-app" python -c "$1" 2>&1)" || status=$?
  printf '%s\n' "$out" | grep -v "No runtime found" || true
  return "$status"
}

step "S3Mock (stand-in S3) with an empty bucket"
docker network create "$NET" >/dev/null
docker run -d --name "$RUN-s3" --network "$NET" -e COM_ADOBE_TESTING_S3MOCK_STORE_INITIAL_BUCKETS=labvault-smoke \
  adobe/s3mock:latest >/dev/null
for _ in $(seq 1 30); do   # wait until it answers
  docker run --rm --network "$NET" curlimages/curl:latest -sf "http://$RUN-s3:9090/" >/dev/null 2>&1 && break
  sleep 1
done

step "1. First start: empty volume, no replica yet"
docker volume create "$RUN-v1" >/dev/null
start_app "$RUN-v1"
wait_healthy

step "2. Write a marker, wait for replication, stop"
# Accounts are seeded on the first page view; do what the app's setup() does.
in_app "from repo.users import seed_users; seed_users(demo=False, admin_password='$ADMIN_PASSWORD')"
in_app "import services; services.log_event('admin', 'SMOKE_TEST', 'Ops', '$MARKER', 'container smoke test')"
sleep 5
started=$(date +%s)
docker stop -t 40 "$RUN-app" >/dev/null
echo "stopped in $(( $(date +%s) - started )) s, exit code $(docker inspect -f '{{.State.ExitCode}}' "$RUN-app")"
docker logs "$RUN-app" 2>&1 | grep -i -E "litestream|sync|replica" | tail -5 || true

step "3. Destroy the container and its volume"
docker rm "$RUN-app" >/dev/null
docker volume rm "$RUN-v1" >/dev/null

step "4. New container, new empty volume: restore from the replica"
docker volume create "$RUN-v2" >/dev/null
start_app "$RUN-v2"
wait_healthy
in_app "
import sqlite3
n = sqlite3.connect('/data/labvault.db').execute(
    \"SELECT COUNT(*) FROM audit_trail WHERE action = 'SMOKE_TEST' AND target_id = '$MARKER'\").fetchone()[0]
assert n == 1, f'marker not restored (found {n})'
print('marker restored')"
docker exec "$RUN-app" python scripts/backup_db.py check /data/labvault.db

step "5. The production image refuses to run as a demo (ADR 0026)"
docker rm -f "$RUN-app" >/dev/null
start_app "$RUN-v2" -e LABVAULT_DEMO_MODE=true
code="$(docker wait "$RUN-app")"
docker logs "$RUN-app" 2>&1 | grep "must not start" || { echo "no refusal in the logs" >&2; exit 1; }
[ "$code" != 0 ] || { echo "container exited 0 in demo mode" >&2; exit 1; }
echo "refused, exit code $code"

step "PASS: data survived the loss of the container and its volume; demo mode refused"
