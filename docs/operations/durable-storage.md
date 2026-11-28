# Runbook: durable storage with Litestream (production)

This runbook implements audit finding C2 and roadmap 5.1 (ADR 0023). LabVault keeps its data in one SQLite file on a **persistent volume**. [Litestream](https://litestream.io) (0.5.x) streams every committed change to **S3-compatible object storage** about once a second. Up to 30 days of history can be restored to a chosen point in time.

The public demo on Streamlit Community Cloud does not use this, because its data is simulated and is rebuilt on restart. The production container and how to deploy it are in [deployment.md](deployment.md) (ADR 0024). Monitoring is roadmap 5.3.

## What you need
| | Example |
|---|---|
| A host with a persistent disk, running **one** app instance | a VM, Fly.io with a volume, Railway with a volume |
| The `litestream` binary | already in the production image, checksum-verified (ADR 0024); for a manual install, use the [release page](https://github.com/benbjohnson/litestream/releases) and check `checksums.txt` |
| A bucket in a **different** provider or region from the host | AWS S3, Cloudflare R2, Backblaze B2 |
| Bucket credentials that can only read and write that bucket | an access key |

## Settings
All settings come from the host's environment or secret store. None of them go in a file in the repository.

| Variable | Value |
|---|---|
| `LABVAULT_DB_PATH` | database on the volume, e.g. `/data/labvault.db` |
| `LITESTREAM_REPLICA_URL` | `s3://<bucket>/labvault/prod`. Use a path for this one database only. |
| `LITESTREAM_S3_ENDPOINT` | only for providers other than AWS, e.g. `https://<account>.r2.cloudflarestorage.com` |
| `LITESTREAM_S3_REGION` | e.g. `us-east-1`, or `auto` for R2 |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | the bucket credentials |
| `LABVAULT_ADMIN_PASSWORD` | initial admin password (secure mode; see the README) |

## Start
```bash
deploy/start.sh            # PORT defaults to 8501
```
1. `litestream restore -if-db-not-exists -if-replica-exists` runs first.
   - The volume is empty, for example a new machine: it brings back the latest replicated state.
   - A database already exists: it is kept.
   - It's the very first start and there is no replica yet: the app starts with an empty database.
2. `litestream replicate -exec "streamlit run app.py …"` runs the app. When the app stops, Litestream makes a final sync.
3. The script **refuses to start** without `LITESTREAM_REPLICA_URL`.
4. In secure mode, the Admin page shows the replica location, or a warning if none is configured.

**Never run two instances against the same bucket path.** Two writers make the replica unrestorable.

## Restore after losing the host or the disk
1. Start a new host with an empty volume and the same settings.
2. Run `deploy/start.sh`. The restore in step 1 of Start is automatic.
3. Run the drill check below on the restored file before letting users back in.
4. Record the restore: who, when, why, and the latest audit entry the check printed.

## Point-in-time restore (bad data, a mistaken change)
Stop the app first, then restore to a **separate file** and inspect it before replacing anything:
```bash
litestream ltx -config deploy/litestream.yml -level all "$LABVAULT_DB_PATH"   # what history exists
litestream restore -config deploy/litestream.yml -timestamp 2026-12-01T09:00:00Z \
  -o /tmp/pitr/labvault.db "$LABVAULT_DB_PATH"
python scripts/backup_db.py check /tmp/pitr/labvault.db
```
To put that file into service:
1. Move the current database and its `-wal`/`-shm` files aside. Never delete them.
2. Copy the restored file to `LABVAULT_DB_PATH`.
3. Run `litestream reset -config deploy/litestream.yml "$LABVAULT_DB_PATH"`, so replication restarts cleanly from the replaced file.
4. Start the app.
5. Record the event, as above.

Don't use `scripts/backup_db.py restore` while Litestream manages the database: it replaces the file underneath Litestream.

## Restore drill (quarterly; acceptance criterion of roadmap 5.1)
On any machine, never over production:
```bash
litestream restore -config deploy/litestream.yml -o /tmp/drill/labvault.db "$LABVAULT_DB_PATH"
python scripts/backup_db.py check /tmp/drill/labvault.db
```
`check` exits non-zero (FAIL) on any of these:
- a failed integrity check;
- foreign-key violations;
- a schema newer than the code;
- a missing integrity trigger (append-only audit trail, second-person signing, the OOS investigation rules).

It also prints row counts and the latest audit entry.

**Pass criteria:**
- `PASS`;
- the counts are in line with production;
- the latest audit entry is within a few seconds of when the drill started.

Record each drill:

| Date | Who | Latest audit entry | Samples / results | Result |
|---|---|---|---|---|
| | | | | |

## Also keep nightly file backups (optional, second line)
`scripts/backup_db.py backup` (see [backup-restore.md](backup-restore.md)) still works on a running database. A nightly copy to a second provider protects against a mistake in the Litestream configuration.
