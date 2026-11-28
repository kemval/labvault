# ADR 0024: One container image; Compose with Caddy on one VM; CI publishes and deploys

- **Status:** Accepted (2026-11-28)
- **Addresses:** roadmap item 5.2 (containerised deployment, secrets, HTTPS, health check).
- **Builds on:** ADR 0023 (SQLite, persistent volume, Litestream).

## Context
Production needs a host with a persistent disk (ADR 0023), and the owner asked for something free. Third-party summaries, checked 2026-11, show:
- Google Cloud's e2-micro (30 GB standard disk) is the most consistently documented always-free VM;
- Oracle's Always Free tier is larger on paper but reported to have shrunk;
- Cloudflare R2's free tier (10 GB, 1 million writes a month, free egress) covers the replica.

Platform-as-a-service free tiers either have no persistent disk or no longer exist. So the design is a plain VM, which avoids lock-in.

## Decision
- **One image** (`Dockerfile`):
  - `python:3.12-slim-bookworm`;
  - dependencies from the hashed lock (`--require-hashes`);
  - Litestream 0.5.18, downloaded at build time and **verified against its published SHA-256** for amd64 and arm64;
  - runs as an unprivileged user (uid 10001), with the database on the `/data` volume;
  - `ENTRYPOINT deploy/start.sh`.
- **No data or secrets in the image:** `.dockerignore` excludes every database file, `.streamlit/secrets.toml`, `.env` files and `.git`.
- **Start-up** (`deploy/start.sh`, extending ADR 0023): restore if the volume is empty, then **create or migrate the schema**, then start Litestream and the app. Before this change, a fresh volume had no schema until the first visitor, so the health check failed and Litestream waited.
- **Health:** `scripts/healthcheck.py` (Docker `HEALTHCHECK`) requires Streamlit's `/_stcore/health` to answer, bypassing any proxy, and the database to open **read-only** with a schema. It never writes.
- **HTTPS:** Caddy 2 in `deploy/compose.yaml` gets and renews the Let's Encrypt certificate for `LABVAULT_DOMAIN`. It redirects HTTP with a 308, adds HSTS, nosniff and a same-origin referrer policy, and passes Streamlit's WebSocket through.
- **Secrets:** only in `deploy/.env` on the server (git-ignored; `.env.example` has empty placeholders) or the host's secret store. CI holds only the SSH deploy credentials, in the `production` environment. App secrets never pass through CI.
- **CI** (`.github/workflows/container.yml`):
  - every PR builds the image and runs `deploy/smoke_test.sh`;
  - `main` publishes `ghcr.io/<owner>/labvault:{latest,sha-<commit>}` for amd64 and arm64;
  - `deploy` runs when `DEPLOY_ENABLED=true`. It copies the Compose files over SSH, with the host key pinned (no `StrictHostKeyChecking=no`), pulls the exact `sha-` image, and fails unless the app is healthy;
  - the one-command redeploy is `gh workflow run Container`.
- **The smoke test is the end-to-end proof of ADR 0023,** with real Litestream and an S3 emulator (S3Mock; MinIO no longer publishes its Docker image):
  1. start, write a marker, then `docker stop`;
  2. destroy the container and its volume;
  3. start a new container on an empty volume: it restores, the marker is present, and `backup_db.py check` passes.
- **Privacy:** `browser.gatherUsageStats = false`, so no usage statistics leave a lab server.
- **Updates:** Dependabot now also watches the Docker base image.

## Consequences
- **One VM, one app container:** that's the single-writer limit from ADR 0023. The `deploy-production` concurrency group stops two deploys from overlapping.
- **Short outage per deploy:** each deploy restarts the app, and active sessions reconnect. Acceptable for one lab; zero-downtime deploys would need two writers.
- **The owner patches the VM's operating system** (enable unattended-upgrades). Monitoring and alerting are 5.3.
- **Validated locally on 2026-11-28 (arm64, Docker 28.5):**
  - the smoke test passed: clean stop in 1 s with exit 0, restore after the volume was destroyed, drill PASS;
  - Compose with Caddy on `localhost`: HTTPS health `ok`, the headers present, an HTTP→HTTPS 308, a WebSocket 101, and the app container healthy.
