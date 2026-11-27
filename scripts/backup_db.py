"""
Back up and restore the LabVault SQLite database (audit C2, interim).
See docs/operations/backup-restore.md for the runbook.

    python scripts/backup_db.py backup labvault.db [--dest DIR] [--keep 14]
    python scripts/backup_db.py restore labvault.db.backup-<timestamp> labvault.db
    python scripts/backup_db.py verify labvault.db.backup-<timestamp>

Backups use SQLite's online backup API, so they are consistent even while the
app is running and include committed changes still in the WAL file. Every
backup is integrity-checked before it is kept. Restore never overwrites: the
current database is moved aside first.
"""

import argparse
import glob
import os
import shutil
import sqlite3
import sys
from datetime import datetime

DEFAULT_KEEP = 14


class BackupError(RuntimeError):
    pass


def _stamp() -> str:
    # Microseconds keep names unique and make name order chronological.
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def verify(path: str) -> None:
    """Raise BackupError unless `path` is a readable, intact SQLite database."""
    if not os.path.isfile(path):
        raise BackupError(f"{path} does not exist")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.execute("SELECT COUNT(*) FROM samples").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        raise BackupError(f"{path} is not a valid LabVault database: {e}") from e
    if result != "ok":
        raise BackupError(f"{path} failed integrity check: {result}")


def _copy(src_path: str, dest_path: str) -> None:
    src = sqlite3.connect(src_path)
    dest = sqlite3.connect(dest_path)
    try:
        src.backup(dest)
        # The copy inherits WAL mode from the source header; switch it back so
        # the backup is one self-contained file with no -wal/-shm companions.
        # (The app re-enables WAL on every connection after a restore.)
        dest.execute("PRAGMA journal_mode = DELETE")
    finally:
        dest.close()
        src.close()


def backup_database(db_path: str, dest_dir: str = None, keep: int = DEFAULT_KEEP) -> str:
    """Write a verified backup of db_path and prune old ones. Returns its path."""
    if not os.path.isfile(db_path):
        raise BackupError(f"{db_path} does not exist")
    dest_dir = dest_dir or os.path.dirname(os.path.abspath(db_path))
    os.makedirs(dest_dir, exist_ok=True)
    prefix = os.path.join(dest_dir, os.path.basename(db_path) + ".backup-")
    path = prefix + _stamp()

    _copy(db_path, path)
    try:
        verify(path)
    except BackupError:
        os.remove(path)
        raise

    if keep:
        backups = sorted(p for p in glob.glob(glob.escape(prefix) + "*") if os.path.isfile(p))
        for old in backups[:-keep]:
            os.remove(old)
    return path


def restore_database(backup_path: str, db_path: str) -> str:
    """
    Replace db_path with backup_path. The app must be stopped.
    The current database (and its -wal/-shm files) is moved aside, never
    deleted. Returns the path it was moved to, or None if there was none.
    """
    verify(backup_path)
    if os.path.abspath(backup_path) == os.path.abspath(db_path):
        raise BackupError("backup and database are the same file")

    moved_to = None
    if os.path.exists(db_path):
        moved_to = f"{db_path}.replaced-{_stamp()}"
        shutil.move(db_path, moved_to)
        for suffix in ("-wal", "-shm"):
            if os.path.exists(db_path + suffix):
                shutil.move(db_path + suffix, moved_to + suffix)

    _copy(backup_path, db_path)
    verify(db_path)
    return moved_to


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backup", help="write a verified backup")
    b.add_argument("db_path")
    b.add_argument("--dest", help="backup directory (default: next to the database)")
    b.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                   help=f"backups to keep, 0 = all (default {DEFAULT_KEEP})")

    r = sub.add_parser("restore", help="restore a backup (stop the app first)")
    r.add_argument("backup_path")
    r.add_argument("db_path")

    v = sub.add_parser("verify", help="integrity-check a backup")
    v.add_argument("path")

    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            print(f"Backup written and verified: {backup_database(args.db_path, args.dest, args.keep)}")
        elif args.command == "restore":
            moved = restore_database(args.backup_path, args.db_path)
            if moved:
                print(f"Previous database moved to {moved}")
            print(f"Restored {args.backup_path} -> {args.db_path}")
        else:
            verify(args.path)
            print(f"{args.path}: ok")
    except BackupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
