"""Backup and restore procedure (audit C2, interim)."""
import glob
import os
import sqlite3

import pytest

from scripts import backup_db


def make_db(path, rows=3):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("CREATE TABLE samples (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO samples (name) VALUES (?)", [(f"s{i}",) for i in range(rows)])
    conn.commit()
    return conn  # left open so committed data may still sit in the WAL


def names(path):
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute("SELECT name FROM samples ORDER BY id")]
    finally:
        conn.close()


def test_backup_includes_committed_wal_data_while_app_is_running(tmp_path):
    db = str(tmp_path / "labvault.db")
    live = make_db(db)
    live.execute("PRAGMA wal_autocheckpoint = 0")
    live.execute("INSERT INTO samples (name) VALUES ('late')")
    live.commit()
    live.execute("BEGIN")
    live.execute("INSERT INTO samples (name) VALUES ('uncommitted')")  # open txn

    path = backup_db.backup_database(db)

    assert names(path) == ["s0", "s1", "s2", "late"]
    backup_db.verify(path)
    live.rollback()
    live.close()


def test_retention_keeps_newest_backups(tmp_path):
    db = str(tmp_path / "labvault.db")
    make_db(db).close()
    paths = [backup_db.backup_database(db, keep=2) for _ in range(4)]
    remaining = sorted(glob.glob(db + ".backup-*"))
    assert remaining == sorted(paths[-2:])


def test_backup_to_separate_directory(tmp_path):
    db = str(tmp_path / "labvault.db")
    make_db(db).close()
    path = backup_db.backup_database(db, dest_dir=str(tmp_path / "backups"))
    assert os.path.dirname(path) == str(tmp_path / "backups")


def test_restore_round_trip_moves_current_db_aside(tmp_path):
    db = str(tmp_path / "labvault.db")
    make_db(db).close()
    backup = backup_db.backup_database(db)

    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM samples")          # simulated data loss
    conn.commit()
    conn.close()

    moved = backup_db.restore_database(backup, db)

    assert names(db) == ["s0", "s1", "s2"]
    assert names(moved) == []                     # the damaged DB is kept, not deleted


def test_corrupt_backup_is_refused_and_live_db_untouched(tmp_path):
    db = str(tmp_path / "labvault.db")
    make_db(db).close()
    bad = tmp_path / "labvault.db.backup-bad"
    bad.write_bytes(b"not a database" * 100)

    with pytest.raises(backup_db.BackupError):
        backup_db.restore_database(str(bad), db)

    assert names(db) == ["s0", "s1", "s2"]
    assert not glob.glob(db + ".replaced-*")


def test_cli_reports_errors_with_exit_code(tmp_path, capsys):
    assert backup_db.main(["verify", str(tmp_path / "missing.db")]) == 1
    assert "does not exist" in capsys.readouterr().err
