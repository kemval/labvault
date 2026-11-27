"""Versioned schema migrations (PRAGMA user_version)."""
import sqlite3
import threading

import pytest


def version(path):
    conn = sqlite3.connect(path)
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    return v


def columns(path, table):
    conn = sqlite3.connect(path)
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    conn.close()
    return cols


def test_migrations_apply_in_order_once(fresh_db):
    calls = []
    migrations = fresh_db.MIGRATIONS + [
        lambda c: (calls.append(1), c.execute("ALTER TABLE samples ADD COLUMN m1 TEXT")),
        lambda c: (calls.append(2), c.execute("ALTER TABLE samples ADD COLUMN m2 TEXT")),
    ]

    fresh_db.apply_migrations(migrations)
    fresh_db.apply_migrations(migrations)  # second run is a no-op

    assert calls == [1, 2]
    assert version(fresh_db.DB_PATH) == len(migrations)
    assert {"m1", "m2"} <= set(columns(fresh_db.DB_PATH, "samples"))


def test_failed_migration_rolls_back_and_keeps_version(fresh_db):
    def bad(c):
        c.execute("ALTER TABLE samples ADD COLUMN half_done TEXT")
        raise RuntimeError("boom")

    before = version(fresh_db.DB_PATH)
    with pytest.raises(RuntimeError):
        fresh_db.apply_migrations(fresh_db.MIGRATIONS + [bad])

    assert version(fresh_db.DB_PATH) == before
    assert "half_done" not in columns(fresh_db.DB_PATH, "samples")


def test_concurrent_startups_apply_each_migration_once(fresh_db):
    calls = []
    barrier = threading.Barrier(2, timeout=10)

    def m(c):
        calls.append(threading.get_ident())
        c.execute("ALTER TABLE samples ADD COLUMN raced TEXT")

    migrations = fresh_db.MIGRATIONS + [m]
    errors = []

    def start():
        barrier.wait()
        try:
            fresh_db.apply_migrations(migrations)
        except Exception as e:  # pragma: no cover - surfaced below
            errors.append(e)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert errors == [] and len(calls) == 1
    assert version(fresh_db.DB_PATH) == len(migrations)


def test_init_db_brings_new_database_to_latest_version(fresh_db):
    assert version(fresh_db.DB_PATH) == len(fresh_db.MIGRATIONS)
