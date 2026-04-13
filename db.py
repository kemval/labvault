"""
db.py — LabVault database layer
Creates all tables and provides helper functions for every module.
Database: SQLite (labvault.db, created automatically on first run)
"""

import sqlite3
import hashlib
import os
from datetime import datetime

DB_PATH = "labvault.db"


# ─────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────────────────────────
# SCHEMA — create all tables
# ─────────────────────────────────────────────

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # USERS
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,          -- SHA-256 hex
            role        TEXT NOT NULL           -- 'admin' | 'lab_tech'
        )
    """)

    # PROTOCOLS — standard test procedures linked to a sample type
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

    # SAMPLES — one row per FDA recall record (or manually registered)
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
            assigned_to         TEXT,                   -- username
            protocol_id         INTEGER,
            notes               TEXT,
            source              TEXT DEFAULT 'FDA',     -- FDA | Manual
            FOREIGN KEY (protocol_id) REFERENCES protocols(id)
        )
    """)

    # TEST RESULTS — one or more results per sample
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

    # AUDIT TRAIL — every action logged here
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

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────

def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def seed_users():
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
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("""
        SELECT * FROM users WHERE username = ? AND password = ?
    """, (username, hash_pw(password))).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT username, role FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lab_techs():
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
    conn = get_conn()
    conn.execute("""
        INSERT INTO audit_trail (timestamp, user, action, module, target_id, detail)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action, module, target_id, detail))
    conn.commit()
    conn.close()


def get_audit_trail(limit: int = 200):
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


def get_all_samples(status_filter=None):
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


def get_sample(sample_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM samples WHERE sample_id = ?", (sample_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_sample_status(sample_id: str, new_status: str, user: str):
    conn = get_conn()
    conn.execute(
        "UPDATE samples SET status = ? WHERE sample_id = ?",
        (new_status, sample_id)
    )
    conn.commit()
    conn.close()
    log_action(user, "STATUS_UPDATED", "Sample Tracking",
               sample_id, f"Status changed to {new_status}")


def update_sample_assignment(sample_id: str, assignee: str, user: str):
    conn = get_conn()
    conn.execute(
        "UPDATE samples SET assigned_to = ? WHERE sample_id = ?",
        (assignee, sample_id)
    )
    conn.commit()
    conn.close()
    log_action(user, "SAMPLE_ASSIGNED", "Sample Tracking",
               sample_id, f"Assigned to {assignee}")


def count_samples_by_status():
    conn = get_conn()
    rows = conn.execute("""
        SELECT status, COUNT(*) as count FROM samples GROUP BY status
    """).fetchall()
    conn.close()
    return {r["status"]: r["count"] for r in rows}


def count_samples_by_priority():
    conn = get_conn()
    rows = conn.execute("""
        SELECT priority, COUNT(*) as count FROM samples GROUP BY priority
    """).fetchall()
    conn.close()
    return {r["priority"]: r["count"] for r in rows}


def sample_exists():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    conn.close()
    return count > 0


# ─────────────────────────────────────────────
# TEST RESULTS
# ─────────────────────────────────────────────

def insert_test_result(data: dict):
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


def get_results_for_sample(sample_id: str):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM test_results WHERE sample_id = ? ORDER BY id DESC
    """, (sample_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_results():
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM test_results ORDER BY id DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_oos_results():
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
    conn = get_conn()
    conn.execute("""
        INSERT INTO protocols
            (name, sample_type, description, steps, created_by, created_at)
        VALUES
            (:name, :sample_type, :description, :steps, :created_by, :created_at)
    """, data)
    conn.commit()
    conn.close()


def get_all_protocols():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM protocols ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_protocol(protocol_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM protocols WHERE id = ?", (protocol_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def seed_protocols():
    """Seed standard GxP protocols used in pharma QC labs."""
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM protocols").fetchone()[0]
    if count > 0:
        conn.close()
        return

    protocols = [
        {
            "name": "Dissolution Testing — USP Apparatus II",
            "sample_type": "Tablet",
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
