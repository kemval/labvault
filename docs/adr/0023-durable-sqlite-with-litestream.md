# ADR 0023: Durable storage: SQLite on a persistent volume, streamed to object storage by Litestream

- **Status:** Accepted (2026-11-28)
- **Addresses:** audit finding C2; roadmap item 5.1.
- **Builds on:** the interim file backups (`scripts/backup_db.py`, `docs/operations/backup-restore.md`), which stay as a second line.

## Context
Streamlit Community Cloud's disk is wiped on every restart and redeploy, so production records did not survive. Roadmap 5.1 asked for managed Postgres or a persistent volume, point-in-time or nightly backups, and a quarterly restore test.

Moving to Postgres would have meant:
- rewriting about 1,800 lines of repository SQL (placeholders, `lastrowid`, `sqlite3.Row`);
- re-implementing the nine integrity triggers and nine migrations;
- replacing `BEGIN IMMEDIATE`, which the import and migration race protection relies on;
- running Postgres in CI.

## Decision (owner's choice: "SQLite + volume + Litestream")
- **Keep SQLite.**
  - One lab's workload is far within a single SQLite file's capacity: the benchmark renders every page in under 100 ms at 10,000 samples (ADR 0020).
  - Every integrity trigger and migration stays exactly as tested.
- **Location:** `LABVAULT_DB_PATH`, from the environment only, because `repo/` must not import Streamlit to read secrets. The default stays `./labvault.db`.
- **Durability per commit:** `PRAGMA synchronous = FULL`, stated explicitly; SQLite's default but not Litestream's suggestion of NORMAL. Every commit a user saw succeed survives a power cut. WAL mode stays (Litestream requires it).
- **Locks:** `busy_timeout` is 5 s (Litestream's recommended value).
- **Continuous backup:** `deploy/start.sh` restores the latest replica if the volume is empty (`-if-db-not-exists -if-replica-exists`), then runs Streamlit under `litestream replicate -exec`.
  - `deploy/litestream.yml` (0.5 syntax: `replica:` singular) takes every value, credentials included, from the environment.
  - It syncs every 1 s, snapshots daily, keeps 720 h (30 days) for point-in-time restore, and validates every 12 h.
  - The script refuses to start without a replica URL.
- **Visibility:** the Admin page shows the database file and the replica location, with credentials stripped. In secure mode without a replica, it shows a warning instead.
- **Restore drill:** `scripts/backup_db.py check` reports integrity, foreign keys, the schema version against the code, all nine integrity triggers, row counts and the latest audit entry, and exits 1 on any problem. `docs/operations/durable-storage.md` gives the quarterly drill, disaster restore and point-in-time restore.

## Consequences
- **One instance only:** SQLite has a single writer, and Litestream needs a single writer per replica path. Horizontal scaling would need Postgres. Revisit if several sites or heavy concurrency appear.
- **Leaving Streamlit Cloud for production:** production needs a host with a persistent disk (packaged in 5.2). The demo can stay on Streamlit Cloud.
- **Loss window:** about 1 s of commits if the host is destroyed between syncs. A clean shutdown makes a final sync.
- **Validation:** the start-up logic was first tested with a stand-in `litestream` binary. Since ADR 0024, `deploy/smoke_test.sh` proves replication and restore with the real binary on every pull request: the data survives destroying the container and its volume.
