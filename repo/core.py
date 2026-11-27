"""
repo/core.py — SQLite connection and transaction handling.
No Streamlit imports anywhere in repo/: it must run in scripts and tests
without a Streamlit runtime. Caching lives in db.py; use cases in services.py.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

# The database lives right next to the app — SQLite just needs a file path.
DB_PATH = "labvault.db"


def get_conn():
    """
    Open a fresh connection to the SQLite database with a couple of
    performance and correctness tweaks applied right away.
    """
    conn = sqlite3.connect(DB_PATH)

    # row_factory turns each row into something that behaves like a dict,
    # so we can do row["column_name"] instead of row[0]. Much more readable.
    conn.row_factory = sqlite3.Row

    # Foreign key enforcement is OFF by default in SQLite — we have to turn
    # it on manually per connection. A bit surprising, but that's SQLite for you.
    conn.execute("PRAGMA foreign_keys = ON")

    # WAL (Write-Ahead Logging) mode lets reads happen at the same time as writes,
    # which is huge for a multi-user app where the dashboard and a form submission
    # might hit the DB simultaneously.
    conn.execute("PRAGMA journal_mode = WAL")

    return conn


@contextmanager
def transaction():
    """
    One connection, one write transaction: commit on success, roll back on
    any exception. BEGIN IMMEDIATE takes the write lock up front so reads
    made inside the block (e.g. a version check) can't go stale before the
    write. Use this for every multi-statement change, including its audit row.
    """
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_in(conn, fn):
    """Run fn(conn) inside the caller's transaction, or in a new one."""
    if conn is not None:
        return fn(conn)
    with transaction() as own:
        return fn(own)


def utc_now() -> str:
    """Current time as UTC ISO-8601, e.g. 2026-11-27T17:30:00Z (matches the column defaults)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
