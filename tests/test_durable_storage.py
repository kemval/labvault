"""Durable storage: database location, durability settings, Litestream start-up and
the restore drill (audit C2, roadmap 5.1, ADR 0023)."""
import os
import sqlite3
import subprocess
import sys
import textwrap

import pytest

import config
from repo import core, schema
from scripts import backup_db
from test_app_login import APP, go, login, no_network, run_app  # noqa: F401

ROOT = os.path.dirname(APP)
START = os.path.join(ROOT, "deploy", "start.sh")


# ── where the database lives ─────────────────────────────────

def test_database_path_comes_from_the_environment(tmp_path):
    target = str(tmp_path / "volume" / "labvault.db")
    code = "import sys; sys.path.insert(0, %r); from repo import core; print(core.DB_PATH)" % ROOT
    env = {**os.environ, "LABVAULT_DB_PATH": target}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert out.stdout.strip() == target
    env.pop("LABVAULT_DB_PATH")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert out.stdout.strip() == "labvault.db"                 # unchanged default


def test_connections_are_durable_and_wait_for_locks(fresh_db):
    conn = core.get_conn()
    try:
        pragma = {p: conn.execute(f"PRAGMA {p}").fetchone()[0]
                  for p in ("journal_mode", "synchronous", "busy_timeout", "foreign_keys")}
    finally:
        conn.close()
    # WAL (required by Litestream), FULL = 2 (every commit fsynced), 5 s lock wait.
    assert pragma == {"journal_mode": "wal", "synchronous": 2, "busy_timeout": 5000,
                      "foreign_keys": 1}


@pytest.mark.parametrize("url, shown", [
    ("s3://labvault-backups/prod", "s3://labvault-backups/prod"),
    ("s3://KEY:SECRET@labvault-backups/prod?region=auto", "s3://labvault-backups/prod"),
    ("", None),
])
def test_the_replica_is_shown_without_credentials(monkeypatch, url, shown):
    monkeypatch.setenv("LITESTREAM_REPLICA_URL", url)
    assert config.backup_replica() == shown


# ── deploy/start.sh, with a stand-in for the litestream binary ─

@pytest.fixture
def fake_litestream(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.txt"
    script = bin_dir / "litestream"
    script.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        printf '%s\\n' "$*" >> {calls}
    """))
    script.chmod(0o755)

    def run(**env):
        full = {"PATH": f"{bin_dir}:/usr/bin:/bin", **env}
        out = subprocess.run(["sh", START], env=full, capture_output=True, text=True)
        lines = calls.read_text().splitlines() if calls.exists() else []
        return out, lines
    return run


def test_start_refuses_to_run_without_a_replica(fake_litestream, tmp_path):
    out, calls = fake_litestream(LABVAULT_DB_PATH=str(tmp_path / "data" / "labvault.db"))
    assert out.returncode != 0 and "refusing to run without a backup replica" in out.stderr
    assert calls == []                                           # nothing started


def test_start_restores_if_needed_then_runs_the_app_under_litestream(fake_litestream,
                                                                     tmp_path):
    db = str(tmp_path / "data" / "labvault.db")
    out, calls = fake_litestream(LABVAULT_DB_PATH=db, LITESTREAM_REPLICA_URL="s3://b/prod",
                                 PORT="8080")
    assert out.returncode == 0, out.stderr
    restore, replicate = calls
    # Never overwrites an existing database; a first-ever start has no replica yet.
    assert restore.startswith("restore -config ")
    assert restore.endswith(f"-if-db-not-exists -if-replica-exists {db}")
    assert replicate.startswith("replicate -config ") and "-exec streamlit run" in replicate
    assert "app.py --server.port 8080" in replicate
    assert os.path.isdir(tmp_path / "data")                      # volume directory created


def test_litestream_config_uses_the_environment_and_keeps_30_days():
    with open(os.path.join(ROOT, "deploy", "litestream.yml")) as f:
        text = f.read()
    for expected in ("path: ${LABVAULT_DB_PATH}", "url: ${LITESTREAM_REPLICA_URL}",
                     "retention: 720h", "replica:"):
        assert expected in text
    assert "secret-access-key" not in text                       # credentials stay in env


# ── the restore drill ────────────────────────────────────────

def test_restore_check_passes_a_complete_database(fresh_db):
    report = backup_db.check(core.DB_PATH)
    assert report["problems"] == []
    assert report["schema_version"] == report["expected_version"] == len(schema.MIGRATIONS)
    assert set(report["counts"]) >= {"samples", "test_results", "audit_trail"}


def test_restore_check_reports_a_missing_integrity_trigger(fresh_db):
    conn = sqlite3.connect(core.DB_PATH)
    conn.execute("DROP TRIGGER audit_trail_no_update")
    conn.commit()
    conn.close()
    assert backup_db.check(core.DB_PATH)["problems"] == ["missing trigger audit_trail_no_update"]
    assert backup_db.main(["check", core.DB_PATH]) == 1


def test_restore_check_refuses_a_database_newer_than_the_code(fresh_db):
    report = backup_db.check(core.DB_PATH, expected_version=len(schema.MIGRATIONS) - 1)
    assert any("newer than this code" in p for p in report["problems"])


# ── the Admin page says whether data is backed up ────────────

def test_admin_page_shows_the_replica(lab_db, settings, monkeypatch):
    settings(demo="true")
    monkeypatch.setenv("LITESTREAM_REPLICA_URL", "s3://KEY:SECRET@labvault-backups/prod")
    at = go(login(run_app(), "admin", "admin123"), "Admin")
    text = " ".join(c.value for c in at.caption)
    assert "Continuous backup (Litestream) to `s3://labvault-backups/prod`" in text
    assert "SECRET" not in text


def test_secure_mode_without_a_replica_warns_the_admin(fresh_db, settings, monkeypatch):
    settings(admin_password="initial-admin-pass-1")
    monkeypatch.delenv("LITESTREAM_REPLICA_URL", raising=False)
    at = go(login(run_app(), "admin", "initial-admin-pass-1"), "Admin")
    assert any("No continuous backup is configured" in w.value for w in at.warning)
