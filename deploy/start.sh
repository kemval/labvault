#!/bin/sh
# Production entry point (ADR 0023): restore the database from object storage
# if this machine has none, then run the app under Litestream, which streams
# every change to the replica and makes a final sync on shutdown.
#
#   LABVAULT_DB_PATH=/data/labvault.db LITESTREAM_REPLICA_URL=s3://bucket/prod deploy/start.sh
#
# Refuses to start without a replica: a production database must be durable.
set -eu

: "${LABVAULT_DB_PATH:?set LABVAULT_DB_PATH to the database on the persistent volume}"
: "${LITESTREAM_REPLICA_URL:?set LITESTREAM_REPLICA_URL (s3://bucket/path); refusing to run without a backup replica}"
case "$LABVAULT_DB_PATH" in /*) ;; *) LABVAULT_DB_PATH="$PWD/$LABVAULT_DB_PATH" ;; esac
export LABVAULT_DB_PATH
export LITESTREAM_S3_ENDPOINT="${LITESTREAM_S3_ENDPOINT:-}"
export LITESTREAM_S3_REGION="${LITESTREAM_S3_REGION:-us-east-1}"

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${LITESTREAM_CONFIG:-$HERE/litestream.yml}"
PORT="${PORT:-8501}"

mkdir -p "$(dirname "$LABVAULT_DB_PATH")"

# Fresh disk: bring back the latest replicated state. Existing database: keep it.
# No replica yet (first ever start): continue with an empty database.
litestream restore -config "$CONFIG" -if-db-not-exists -if-replica-exists "$LABVAULT_DB_PATH"

# Create or migrate the schema now (ADR 0003), so Litestream replicates a real
# database from the start and the health check passes before the first visitor.
cd "$HERE/.."
"${PYTHON:-python}" -c "from repo.schema import init_db; init_db()"

exec litestream replicate -config "$CONFIG" \
  -exec "streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true"
