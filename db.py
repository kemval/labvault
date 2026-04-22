"""
db.py — LabVault database layer
Creates all tables and provides helper functions for every module.
Database: SQLite (labvault.db, created automatically on first run)
"""

import sqlite3
import hashlib
from datetime import datetime
import streamlit as st

# The database lives right next to the app — SQLite just needs a file path.
# On Streamlit Cloud this path is relative to the working directory.
DB_PATH = "labvault.db"


# ─────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# SCHEMA — create all tables + performance indexes
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# CACHE HELPERS — called after writes to keep UI in sync
# ─────────────────────────────────────────────

def _clear_sample_cache():
    """
    After any write to the samples table, we need to bust all the
    related caches so the UI shows fresh data on the next render.
    Streamlit's @st.cache_data caches are per-function, so we clear them individually.
    """
    get_all_samples.clear()
    get_recent_samples.clear()
    count_samples_by_status.clear()
    count_samples_by_priority.clear()
    sample_exists.clear()


def _clear_result_cache():
    """Same idea for test result caches — any new result clears all of these."""
    get_all_results.clear()
    get_oos_results.clear()
    count_oos_results.clear()
    get_results_for_sample.clear()


# ─────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────

def hash_pw(password: str) -> str:
    """SHA-256 hash a password. Simple, fast, and one-way — passwords never stored raw."""
    return hashlib.sha256(password.encode()).hexdigest()


def seed_users():
    """
    Insert the default user accounts on first run.
    INSERT OR IGNORE means running this again won't duplicate anything —
    totally safe to call on every startup.
    """
    conn = get_conn()
    c = conn.cursor()
    users = [
        ("admin",    hash_pw("admin123"),   "admin"),
        ("kembly",   hash_pw("lab2024"),    "lab_tech"),
        ("carlos",   hash_pw("lab2024"),    "lab_tech"),
        ("maria",    hash_pw("lab2024"),    "lab_tech"),
    ]
    for u in users:
        c.execute("""
            INSERT OR IGNORE INTO users (username, password, role)
            VALUES (?, ?, ?)
        """, u)
    conn.commit()
    conn.close()


def authenticate(username: str, password: str):
    """
    Look up a user by username + hashed password.
    Returns the full user row as a dict, or None if credentials don't match.
    We hash the input before querying so the DB never sees a plaintext password.
    """
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("""
        SELECT * FROM users WHERE username = ? AND password = ?
    """, (username, hash_pw(password))).fetchone()
    conn.close()
    return dict(row) if row else None


@st.cache_data(ttl=300)
def get_all_users():
    """Fetch all users — just username and role, no password hashes leaving the DB."""
    conn = get_conn()
    rows = conn.execute("SELECT username, role FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@st.cache_data(ttl=300)
def get_lab_techs():
    """
    Return a list of lab tech usernames — used to populate assignment dropdowns.
    Cached for 5 minutes since user accounts rarely change mid-session.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT username FROM users WHERE role = 'lab_tech'"
    ).fetchall()
    conn.close()
    return [r["username"] for r in rows]


# ─────────────────────────────────────────────
# AUDIT TRAIL
# ─────────────────────────────────────────────

def log_action(user: str, action: str, module: str, target_id: str = "", detail: str = ""):
    """
    Write a single audit record for any action that changes data.
    Called after every insert/update — never skip this, it's what makes
    the system traceable and GxP-compliant.
    Also clears the audit trail cache so the Audit Trail page refreshes.
    """
    conn = get_conn()
    conn.execute("""
        INSERT INTO audit_trail (timestamp, user, action, module, target_id, detail)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action, module, target_id, detail))
    conn.commit()
    conn.close()
    # Bust the audit cache immediately so the next page load shows this entry
    get_audit_trail.clear()


@st.cache_data(ttl=30)
def get_audit_trail(limit: int = 200):
    """
    Fetch the most recent audit entries, newest first.
    Short TTL of 30s — audit logs should feel close to real-time.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM audit_trail ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# SAMPLES
# ─────────────────────────────────────────────

def insert_sample(data: dict):
    """
    Insert a new sample row. INSERT OR IGNORE means duplicate sample_ids
    (from re-importing the same FDA record) are silently skipped —
    no errors, no duplicates, exactly what we want.
    """
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO samples
            (sample_id, product_name, lot_number, manufacturer, sample_type,
             recall_class, priority, reason_for_recall, collection_date,
             status, assigned_to, protocol_id, notes, source)
        VALUES
            (:sample_id, :product_name, :lot_number, :manufacturer, :sample_type,
             :recall_class, :priority, :reason_for_recall, :collection_date,
             :status, :assigned_to, :protocol_id, :notes, :source)
    """, data)
    conn.commit()
    conn.close()
    _clear_sample_cache()


@st.cache_data(ttl=30)
def get_all_samples(status_filter=None):
    """
    Fetch all samples, optionally filtered by status.
    The index on status makes the filtered query very fast even with many rows.
    Cached for 30s — short enough to feel fresh, long enough to avoid hammering the DB.
    """
    conn = get_conn()
    if status_filter and status_filter != "All":
        rows = conn.execute(
            "SELECT * FROM samples WHERE status = ? ORDER BY id DESC", (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM samples ORDER BY id DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@st.cache_data(ttl=30)
def get_recent_samples(limit: int = 8):
    """
    A lightweight version of get_all_samples — only fetches the columns
    the dashboard actually needs, and only the N most recent rows.
    No point pulling all 100 columns × 100 rows just to show 8 cards.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT sample_id, product_name, manufacturer, status, priority, assigned_to "
        "FROM samples ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sample(sample_id: str):
    """Look up a single sample by its ID. Not cached — used for detail views that need live data."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM samples WHERE sample_id = ?", (sample_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_sample_status(sample_id: str, new_status: str, user: str):
    """
    Update just the status column on a sample, then log the change
    in the audit trail. The cache clear ensures the tracking page
    reflects the new status immediately.
    """
    conn = get_conn()
    conn.execute(
        "UPDATE samples SET status = ? WHERE sample_id = ?",
        (new_status, sample_id)
    )
    conn.commit()
    conn.close()
    log_action(user, "STATUS_UPDATED", "Sample Tracking",
               sample_id, f"Status changed to {new_status}")
    _clear_sample_cache()


def update_sample_assignment(sample_id: str, assignee: str, user: str):
    """Reassign a sample to a different lab tech and record who made the change."""
    conn = get_conn()
    conn.execute(
        "UPDATE samples SET assigned_to = ? WHERE sample_id = ?",
        (assignee, sample_id)
    )
    conn.commit()
    conn.close()
    log_action(user, "SAMPLE_ASSIGNED", "Sample Tracking",
               sample_id, f"Assigned to {assignee}")
    _clear_sample_cache()


@st.cache_data(ttl=30)
def count_samples_by_status():
    """
    GROUP BY query that returns a dict like {"Pending": 12, "Completed": 45, ...}.
    Used by the dashboard KPI cards and bar chart. Much cheaper than loading all rows.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT status, COUNT(*) as count FROM samples GROUP BY status
    """).fetchall()
    conn.close()
    return {r["status"]: r["count"] for r in rows}


@st.cache_data(ttl=30)
def count_samples_by_priority():
    """Same pattern as count_samples_by_status but grouped by priority level."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT priority, COUNT(*) as count FROM samples GROUP BY priority
    """).fetchall()
    conn.close()
    return {r["priority"]: r["count"] for r in rows}


@st.cache_data(ttl=60)
def sample_exists():
    """
    Quick boolean check — is there at least one sample in the DB?
    Used on startup to decide whether to run the auto-import.
    COUNT(*) on an indexed table is nearly instant.
    """
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    conn.close()
    return count > 0


# ─────────────────────────────────────────────
# TEST RESULTS
# ─────────────────────────────────────────────

def insert_test_result(data: dict):
    """
    Insert a new test result row and clear the result cache.
    No IGNORE here — duplicate results are allowed (a sample can be re-tested).
    """
    conn = get_conn()
    conn.execute("""
        INSERT INTO test_results
            (sample_id, test_name, result_value, result_unit,
             spec_min, spec_max, status, tested_by, tested_at, notes)
        VALUES
            (:sample_id, :test_name, :result_value, :result_unit,
             :spec_min, :spec_max, :status, :tested_by, :tested_at, :notes)
    """, data)
    conn.commit()
    conn.close()
    _clear_result_cache()


@st.cache_data(ttl=30)
def get_results_for_sample(sample_id: str):
    """Fetch all test results for a specific sample, newest first."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM test_results WHERE sample_id = ? ORDER BY id DESC
    """, (sample_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@st.cache_data(ttl=30)
def get_all_results():
    """
    Fetch every test result in the system — used by Reports.
    Potentially a big query, but Reports is an explicit user action,
    not a background poll, so the load is acceptable.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM test_results ORDER BY id DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@st.cache_data(ttl=30)
def get_oos_results(limit: int = 10):
    """
    Fetch only the Out-of-Spec results — cheaper than loading everything and
    filtering in Python. The index on test_results.status makes this fast.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT sample_id, test_name, result_value, result_unit,
               spec_min, spec_max, tested_by, tested_at
        FROM   test_results
        WHERE  status = 'Fail (OOS)'
        ORDER  BY id DESC
        LIMIT  ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@st.cache_data(ttl=30)
def count_oos_results():
    """
    Count of OOS results — used as a KPI metric on the dashboard.
    A single COUNT(*) is much faster than fetching all rows and len()-ing them.
    """
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM test_results WHERE status = 'Fail (OOS)'"
    ).fetchone()[0]
    conn.close()
    return count


# ─────────────────────────────────────────────
# PROTOCOLS
# ─────────────────────────────────────────────

def insert_protocol(data: dict):
    """Insert a new protocol and immediately clear the protocol cache."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO protocols
            (name, sample_type, description, steps, created_by, created_at)
        VALUES
            (:name, :sample_type, :description, :steps, :created_by, :created_at)
    """, data)
    conn.commit()
    conn.close()
    get_all_protocols.clear()


@st.cache_data(ttl=300)
def get_all_protocols():
    """
    Fetch all protocols. Long TTL of 5 minutes — protocols are rarely modified
    once the lab is up and running, so we can afford to cache them longer.
    """
    conn = get_conn()
    rows = conn.execute("SELECT * FROM protocols ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_protocol(protocol_id: int):
    """Look up a single protocol by ID — not cached since it's rarely needed."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM protocols WHERE id = ?", (protocol_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def seed_protocols():
    """
    Pre-load standard GxP test protocols used in pharmaceutical QC labs.
    These are based on real USP/ICH guidelines — Dissolution, Potency, Sterility, pH, Microbial.
    Runs only once: if the protocols table already has rows, we skip entirely.
    """
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM protocols").fetchone()[0]
    if count > 0:
        conn.close()
        return  # already seeded, nothing to do

    protocols = [
        {
            "name": "Dissolution Testing — USP Apparatus II",
            "sample_type": "Tablet",
            # This test is mandatory for all solid oral dosage forms — it tells us
            # whether the drug actually dissolves and can be absorbed by the body.
            "description": "Measures the rate and extent of drug release from solid oral dosage forms. Required for all solid oral products per USP <711>.",
            "steps": "\n".join([
                "1. Prepare dissolution medium (900 mL of 0.1N HCl or pH 6.8 buffer) at 37°C ± 0.5°C",
                "2. Set paddle speed to 50 RPM",
                "3. Place one tablet per vessel",
                "4. Collect samples at 15, 30, 45, and 60 minutes",
                "5. Filter samples through 0.45 µm membrane filter",
                "6. Analyze by UV spectrophotometry or HPLC",
                "7. Calculate % drug released at each time point",
                "8. Accept if ≥80% released at 60 minutes (Q = 80%)",
                "9. Document all results in the test result log",
            ]),
            "created_by": "admin",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "name": "Potency Assay — HPLC Method",
            "sample_type": "Tablet",
            # HPLC (High-Performance Liquid Chromatography) is the gold standard
            # for measuring how much active ingredient is actually in the pill.
            "description": "Determines the amount of active pharmaceutical ingredient (API) present in the sample. Acceptance: 90.0%–110.0% of label claim.",
            "steps": "\n".join([
                "1. Prepare reference standard solution at known concentration",
                "2. Prepare sample: weigh 20 tablets, calculate average weight",
                "3. Dissolve equivalent of one tablet weight in diluent",
                "4. Sonicate for 15 minutes, filter through 0.22 µm filter",
                "5. Inject standard and sample solutions into HPLC system",
                "6. Column: C18, 150mm x 4.6mm, 5µm particle size",
                "7. Mobile phase: Acetonitrile:Buffer (40:60)",
                "8. Flow rate: 1.0 mL/min, UV detection at 254 nm",
                "9. Calculate % label claim from peak areas",
                "10. Accept if result is 90.0%–110.0%",
            ]),
            "created_by": "admin",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "name": "Sterility Testing — Membrane Filtration",
            "sample_type": "Injectable",
            # For injectables, any microbial contamination can be life-threatening —
            # hence the 14-day incubation period to catch slow-growing organisms.
            "description": "Verifies absence of viable microorganisms in sterile pharmaceutical products per USP <71>.",
            "steps": "\n".join([
                "1. Perform all testing in ISO Class 5 laminar flow hood",
                "2. Prepare culture media: Fluid Thioglycollate (FTM) and Soybean Casein Digest (SCDB)",
                "3. Filter entire sample volume through 0.45 µm membrane",
                "4. Transfer membrane to both FTM and SCDB media",
                "5. Incubate FTM at 30–35°C for 14 days",
                "6. Incubate SCDB at 20–25°C for 14 days",
                "7. Inspect daily for turbidity or microbial growth",
                "8. Accept if no growth observed at 14 days",
                "9. If growth observed: invalidate or fail — initiate deviation report",
            ]),
            "created_by": "admin",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "name": "pH Measurement — USP <791>",
            "sample_type": "Liquid",
            # pH affects everything: drug stability, patient comfort, absorption rate.
            # Even a small drift outside spec can compromise the product.
            "description": "Determines pH of liquid pharmaceutical preparations. Critical for product stability, efficacy, and patient safety.",
            "steps": "\n".join([
                "1. Calibrate pH meter with two buffer solutions bracketing expected sample pH",
                "2. Rinse electrode with purified water, blot dry",
                "3. Immerse electrode in sample at room temperature (20–25°C)",
                "4. Allow reading to stabilize (minimum 30 seconds)",
                "5. Record pH to two decimal places",
                "6. Rinse electrode, repeat measurement — values must agree within ±0.05",
                "7. Report mean of two readings",
                "8. Compare to specification range in product monograph",
            ]),
            "created_by": "admin",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "name": "Microbial Limits Testing — USP <61>/<62>",
            "sample_type": "Non-sterile",
            # Non-sterile products (like oral tablets) aren't required to be
            # completely free of microbes — but they still have limits.
            # TAMC and TYMC are the standard counts pharma labs track.
            "description": "Determines total aerobic microbial count (TAMC) and total yeast/mold count (TYMC) in non-sterile products.",
            "steps": "\n".join([
                "1. Prepare sample: dissolve/dilute in buffered sodium chloride-peptone solution",
                "2. Perform serial 10-fold dilutions as needed",
                "3. TAMC: plate on Soybean Casein Digest Agar, incubate 30–35°C for 5 days",
                "4. TYMC: plate on Sabouraud Dextrose Agar, incubate 20–25°C for 5 days",
                "5. Count colonies after incubation",
                "6. Calculate CFU/g or CFU/mL",
                "7. Accept TAMC ≤ 1000 CFU/g (oral), TYMC ≤ 100 CFU/g (oral)",
                "8. Check for absence of specified microorganisms (E. coli, Salmonella)",
                "9. Document all plate counts and calculations",
            ]),
            "created_by": "admin",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    ]

    for p in protocols:
        conn.execute("""
            INSERT INTO protocols (name, sample_type, description, steps, created_by, created_at)
            VALUES (:name, :sample_type, :description, :steps, :created_by, :created_at)
        """, p)

    conn.commit()
    conn.close()
