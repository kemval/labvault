# Runbook — Database backup & restore (interim)

Addresses audit finding C2 until the database moves to durable managed storage
(roadmap 5.1). Tool: `scripts/backup_db.py`. It uses only the standard
library; run it with the app's Python.

## ⚠️ Scope: where this protects you
| Deployment | Protected? |
|---|---|
| Local or self-hosted, with backups on a different disk or machine | ✅ Yes |
| Local or self-hosted, with backups on the same disk | ⚠️ Protects against bad data or mistakes, not disk loss |
| **Streamlit Community Cloud** | ❌ **No.** The app's disk, and any backups on it, are lost on reboot or redeploy. Treat that instance as disposable demo data. |

## Take a backup
Safe while the app is running. It uses SQLite's online backup API and
includes committed changes that are still in the WAL file.

```bash
python scripts/backup_db.py backup labvault.db --dest /path/to/backups --keep 14
```

- Each backup is a single self-contained file:
  `labvault.db.backup-YYYYMMDD-HHMMSS-ffffff`.
- Each backup is integrity-checked (`PRAGMA integrity_check`) before it is
  kept. A failed check deletes the copy and exits with code 1.
- `--keep N` keeps the newest N backups in `--dest`; `0` keeps all.

### Schedule it (example: nightly at 02:00, cron)
```cron
0 2 * * * cd /opt/labvault && .venv/bin/python scripts/backup_db.py backup labvault.db --dest /mnt/backup/labvault --keep 14 >> /var/log/labvault-backup.log 2>&1
```
Alert on a non-zero exit code, or on a log with no "verified" line in the
last 26 h.

## Restore
1. **Stop the app.** A restore while it is running can lose writes.
2. Verify the backup you intend to use:
   ```bash
   python scripts/backup_db.py verify /path/to/backups/labvault.db.backup-<timestamp>
   ```
3. Restore:
   ```bash
   python scripts/backup_db.py restore /path/to/backups/labvault.db.backup-<timestamp> labvault.db
   ```
   The current database and its `-wal`/`-shm` files are **moved aside** to
   `labvault.db.replaced-<timestamp>`, never deleted. The restored file is
   verified again.
4. Start the app. Pending schema migrations (ADR 0003) are applied
   automatically on start.
5. Record the restore: who, when, which backup, and why. It is a GxP-relevant
   event and the audit trail inside the restored database won't contain it.

## Restore drill (quarterly)
Restore the latest backup into a scratch location (never over production),
then check:
```bash
python scripts/backup_db.py restore <latest-backup> /tmp/drill/labvault.db
sqlite3 /tmp/drill/labvault.db "SELECT COUNT(*) FROM samples; SELECT COUNT(*) FROM test_results; SELECT MAX(timestamp) FROM audit_trail;"
```
Pass criteria: the counts match expectations, and the latest audit timestamp
is within one backup interval of when the backup was taken. Last performed:
2026-11-27, on a copy of the development database (255 samples and 286
results restored, app opened it at schema v1).
