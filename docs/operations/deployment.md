# Runbook: deploying LabVault to production (one VM, free tier)

This runbook covers roadmap 5.2 (ADR 0024). It runs one VM with Docker Compose and two containers:
- **labvault**: the app, Litestream and a health check;
- **caddy**: automatic HTTPS.

The database is on a Docker volume and is streamed to object storage (ADR 0023, [durable-storage.md](durable-storage.md)). CI builds, tests and publishes the image, and can deploy it.

## The free setup (as of 2026-11; check each provider's current terms)
| Part | Free option | Watch |
|---|---|---|
| VM | Google Cloud **e2-micro**, Always Free in us-west1, us-central1 or us-east1, with a 30 GB disk | The boot disk must be **"Standard persistent disk"**, not the default "Balanced". It has 1 GB of RAM, and about 1 GB a month of free outbound traffic. |
| Alternative VM | Oracle Cloud Always Free (AMD micro or Arm) | The free allowances have been reported to shrink. |
| Backup bucket | **Cloudflare R2**: 10 GB, 1 million writes a month, no egress fees | Litestream writes only when data changes; check the R2 usage page in the first weeks. |
| HTTPS name | a free **DuckDNS** subdomain, or any domain you own | Its DNS A record must point at the VM's static IP. |

Both VM providers ask for a payment card to verify the account, even on the free tier.

### Current status, and options without a payment card
**Current status (2026-11-28, owner's decision):** LabVault runs only as the public **demo** on Streamlit Community Cloud. It holds simulated data, needs no card, and is rebuilt on restart. This production setup is built and tested (ADR 0023, ADR 0024), ready for when an organisation hosts LabVault on an account it controls.

Hosts that reportedly need no card: Render's free web service and Hugging Face Spaces (Docker); for buckets, Backblaze B2 and Tigris. Check each at sign-up. They have **no persistent disk** and sleep when idle. `start.sh` restores from the bucket on every start, so data survives, but:
- a kill without a stop signal can lose about 1 s of changes;
- a platform that starts the new version **before** stopping the old one (Render does) briefly has **two writers to one replica**, which can make it unrestorable;
- there's no service agreement for lab records.

These hosts suit a showcase. Use them for real records only after adding a guard against two writers. Set a **budget alert** of $1 in the provider's billing settings so any charge is noticed immediately.

## 1. One-time server setup
1. **Create the VM.**
   - Use Debian 12, e2-micro, a standard persistent disk and a static external IP.
   - Allow inbound 22 (from your IP only, if you can), 80 and 443.
2. **Install Docker** (Docker's convenience script or the Debian packages). Then:
   ```bash
   sudo usermod -aG docker "$USER"            # log out and in again
   sudo mkdir -p /opt/labvault && sudo chown "$USER" /opt/labvault
   ```
   On a 1 GB VM, add 1 GB of swap so image pulls don't run out of memory.
3. **Create the bucket and an API token** limited to that bucket. For R2, the endpoint is `https://<account-id>.r2.cloudflarestorage.com` and the region is `auto`.
4. **Fill in the settings.** Copy `deploy/compose.yaml`, `deploy/Caddyfile` and `deploy/.env.example` to `/opt/labvault/`. Rename `.env.example` to `.env` and fill it in; it holds the app's only secrets. Then run `chmod 600 /opt/labvault/.env`.
5. **Allow the image to be pulled.** Either make the GHCR package public (**GitHub → Packages → labvault → Package settings → Change visibility**; the code is public anyway), or run `docker login ghcr.io` on the VM with a token that can only read packages.
6. **Start it:**
   ```bash
   cd /opt/labvault && docker compose up -d
   docker compose ps                        # labvault should become "healthy"
   ```
7. **Check it.** Open `https://<your-domain>` and sign in as `admin` with `LABVAULT_ADMIN_PASSWORD`. The instance starts **empty**: production never imports the FDA demo data, and the image can't run in demo mode (ADR 0026). If the container exits at once, `docker compose logs labvault` shows the reason after "LabVault must not start:". Create a second admin account (README, Configuration). The **Admin** page must show "Continuous backup (Litestream) to s3://…".

## 2. Deploys from CI (the one command)
**Settings → Environments → New environment "production".** Add these secrets:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | the VM's IP or DNS name |
| `DEPLOY_USER` | the VM user that is in the `docker` group |
| `DEPLOY_SSH_KEY` | a private key used only for deploys; its public key goes in that user's `~/.ssh/authorized_keys` |
| `DEPLOY_KNOWN_HOSTS` | the output of `ssh-keyscan <host>`, checked against the VM's real fingerprint |

Add **"Required reviewers"** to the environment if every deploy should need a click. Then set the repository variable `DEPLOY_ENABLED=true` (**Settings → Secrets and variables → Actions → Variables**).

After that:
- every merge to `main` builds, smoke-tests, publishes `sha-<commit>` and deploys it;
- to redeploy by hand, run `gh workflow run Container`, or use **Actions → Container → Run workflow**.

The deploy copies `compose.yaml` and `Caddyfile`, pulls the exact `sha-` image, restarts the app, and fails unless the app is healthy within about 3 minutes. Stopping the old container gives Litestream up to 40 s for its final sync.

## Roll back
Redeploy the previous commit's image on the VM:
```bash
cd /opt/labvault
echo 'LABVAULT_IMAGE=ghcr.io/kemval/labvault:sha-<previous commit>' > image.env
docker compose --env-file image.env up -d
```
If the newer release added a schema migration, the older code has not been tested against the newer schema. Try the rollback on a restored copy first (durable-storage.md, restore drill), or restore the database to a point before the upgrade.

## Health
- Docker marks the container `unhealthy` if Streamlit stops answering `/_stcore/health`, or if the database can't be read (`scripts/healthcheck.py`).
- `docker compose ps` shows it. Alerting on it is roadmap 5.3.

## Logs
```bash
docker compose logs -f labvault       # JSON app logs (ADR 0021) and Litestream
grep <reference>                      # find a user-reported error reference
```
