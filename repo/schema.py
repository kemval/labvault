"""
repo/schema.py — baseline schema and versioned migrations (ADR 0003).
"""

from datetime import datetime

from repo.core import get_conn


def init_db():
    """
    Create all tables if they don't already exist, then add indexes
    on the columns we filter and sort by most often.
    Safe to call on every startup — CREATE IF NOT EXISTS is idempotent.
    """
    conn = get_conn()
    c = conn.cursor()

    # USERS — just enough to authenticate and show role-based UI
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,          -- SHA-256 hex (never store plaintext!)
            role        TEXT NOT NULL           -- 'admin' | 'lab_tech'
        )
    """)

    # PROTOCOLS — the standard test procedures a sample can be assigned to.
    # Steps are stored as a single newline-separated string because they're
    # always read together and never queried individually.
    c.execute("""
        CREATE TABLE IF NOT EXISTS protocols (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            sample_type     TEXT NOT NULL,
            description     TEXT,
            steps           TEXT,               -- newline-separated steps
            created_by      TEXT,
            created_at      TEXT
        )
    """)

    # SAMPLES — the heart of the system. One row per FDA recall record (or
    # manually registered sample). All downstream test results reference this table.
    c.execute("""
        CREATE TABLE IF NOT EXISTS samples (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id           TEXT UNIQUE NOT NULL,   -- e.g. D-0318-2024
            product_name        TEXT NOT NULL,
            lot_number          TEXT,
            manufacturer        TEXT,
            sample_type         TEXT,                   -- e.g. Tablet, Capsule
            recall_class        TEXT,                   -- Class I / II / III
            priority            TEXT,                   -- Critical / Major / Minor
            reason_for_recall   TEXT,
            collection_date     TEXT,
            status              TEXT DEFAULT 'Pending', -- Pending/In Progress/Completed/Rejected
            assigned_to         TEXT,                   -- username of the responsible tech
            protocol_id         INTEGER,
            notes               TEXT,
            source              TEXT DEFAULT 'FDA',     -- FDA | Manual
            FOREIGN KEY (protocol_id) REFERENCES protocols(id)
        )
    """)

    # TEST RESULTS — one or more results per sample; each test is recorded
    # individually so we can flag specific failures (OOS = Out Of Spec).
    c.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id       TEXT NOT NULL,
            test_name       TEXT NOT NULL,      -- e.g. Dissolution, Potency
            result_value    REAL,
            result_unit     TEXT,               -- e.g. %, CFU/mL, pH
            spec_min        REAL,
            spec_max        REAL,
            status          TEXT,               -- Pass | Fail (OOS)
            tested_by       TEXT,
            tested_at       TEXT,
            notes           TEXT,
            FOREIGN KEY (sample_id) REFERENCES samples(sample_id)
        )
    """)

    # AUDIT TRAIL — every write action in the system gets a row here.
    # This is what makes LabVault GxP-compliant: nothing gets silently changed.
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_trail (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            user        TEXT NOT NULL,
            action      TEXT NOT NULL,          -- e.g. SAMPLE_CREATED
            module      TEXT NOT NULL,          -- e.g. Sample Intake
            target_id   TEXT,                   -- sample_id or protocol id
            detail      TEXT                    -- human-readable description
        )
    """)

    # ── PERFORMANCE INDEXES ──────────────────────────────────
    # Without these, every filter and status lookup would do a full table scan.
    # With 100+ samples they're already noticeably faster — at 10,000+ they're essential.
    c.execute("CREATE INDEX IF NOT EXISTS idx_samples_status   ON samples(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_samples_priority ON samples(priority)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_samples_id       ON samples(sample_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_results_sample   ON test_results(sample_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_results_status   ON test_results(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp  ON audit_trail(timestamp)")
    # ────────────────────────────────────────────────────────

    conn.commit()
    conn.close()

    apply_migrations()


def _m001_simulated_flag(conn):
    """Audit C4: mark demo data so it can't be mistaken for real QC records."""
    from seed import SIMULATOR_NOTES  # lazy: seed imports this module

    conn.execute("ALTER TABLE samples ADD COLUMN is_simulated INTEGER NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE test_results ADD COLUMN is_simulated INTEGER NOT NULL DEFAULT 0")

    # Every FDA-imported sample is demo data (invented lot, assignee, status).
    n_samples = conn.execute(
        "UPDATE samples SET is_simulated = 1 WHERE source = 'FDA'").rowcount

    # Only results in the simulator's exact wording; anything logged by hand
    # against a demo sample stays a real entry.
    rows = conn.execute("""
        SELECT t.id, t.notes FROM test_results t
        JOIN samples s ON s.sample_id = t.sample_id
        WHERE s.source = 'FDA'
    """).fetchall()
    result_ids = [(r["id"],) for r in rows if SIMULATOR_NOTES.match(r["notes"] or "")]
    conn.executemany("UPDATE test_results SET is_simulated = 1 WHERE id = ?", result_ids)

    if n_samples or result_ids:
        conn.execute("""
            INSERT INTO audit_trail (timestamp, user, action, module, target_id, detail)
            VALUES (?, 'system', 'SCHEMA_MIGRATED', 'Database', 'migration 1', ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              f"Flagged {n_samples} FDA-imported samples and {len(result_ids)} "
              f"simulator-generated test results as simulated (audit C4)."))


def _m002_sample_version(conn):
    """Audit H8: row version for optimistic concurrency on sample updates."""
    conn.execute("ALTER TABLE samples ADD COLUMN version INTEGER NOT NULL DEFAULT 1")


MIGRATIONS = [
    _m001_simulated_flag,
    _m002_sample_version,
]


def schema_version(conn) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def apply_migrations(migrations=None):
    """
    Apply pending migrations, each in its own transaction. BEGIN IMMEDIATE
    takes the write lock before the version is re-read, so two processes
    starting together can't apply the same migration twice.
    """
    migrations = MIGRATIONS if migrations is None else migrations
    conn = get_conn()
    try:
        for version, migrate in enumerate(migrations, start=1):
            conn.execute("BEGIN IMMEDIATE")
            try:
                if schema_version(conn) >= version:
                    conn.rollback()
                    continue
                migrate(conn)
                conn.execute(f"PRAGMA user_version = {int(version)}")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
    finally:
        conn.close()
