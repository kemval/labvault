"""
repo/schema.py — baseline schema and versioned migrations (ADR 0003).
"""

from datetime import datetime

from repo import passwords
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


class MigrationError(RuntimeError):
    """Existing data can't be migrated safely; nothing was changed."""


# Frozen copies of the allowed values as of migration 3. A released migration
# must never change, so these are deliberately not imported from elsewhere.
_M003_ROLES = ("admin", "lab_tech", "system")
_M003_STATUSES = ("Pending", "In Progress", "Completed", "Rejected")
_M003_PRIORITIES = ("Critical", "Major", "Minor")
_M003_CLASSES = ("Class I", "Class II", "Class III")
_M003_SAMPLE_TYPES = ("Tablet", "Capsule", "Injectable", "Liquid", "Topical", "Powder",
                      "Non-sterile")
_M003_SOURCES = ("FDA", "Manual")
_M003_RESULT_STATUSES = ("Pass", "Fail (OOS)")
# Non-login accounts that own automated actions. "!" can never equal a
# SHA-256 hex digest, and authenticate() also refuses the system role.
_M003_SYSTEM_ACCOUNTS = ("system", "simulator")
_UNUSABLE_PASSWORD = "!"
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"


def _sql_list(values):
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + ")"


def _m003_problems(conn):
    """Every existing row that would break a migration-3 rule, described."""
    users = "(SELECT username FROM users)"
    checks = [
        ("users.role", "role", "users", f"role NOT IN {_sql_list(_M003_ROLES)}"),
        ("samples.status", "status", "samples",
         f"status IS NULL OR status NOT IN {_sql_list(_M003_STATUSES)}"),
        ("samples.priority", "priority", "samples",
         f"priority NOT IN {_sql_list(_M003_PRIORITIES)}"),
        ("samples.recall_class", "recall_class", "samples",
         f"recall_class NOT IN {_sql_list(_M003_CLASSES)}"),
        ("samples.sample_type", "sample_type", "samples",
         f"sample_type NOT IN {_sql_list(_M003_SAMPLE_TYPES)}"),
        ("samples.source", "source", "samples",
         f"source IS NULL OR source NOT IN {_sql_list(_M003_SOURCES)}"),
        ("samples.assigned_to (not a user)", "assigned_to", "samples",
         f"assigned_to IS NOT NULL AND assigned_to NOT IN {users}"),
        ("samples.protocol_id (no such protocol)", "protocol_id", "samples",
         "protocol_id IS NOT NULL AND protocol_id NOT IN (SELECT id FROM protocols)"),
        ("test_results.status", "status", "test_results",
         f"status IS NULL OR status NOT IN {_sql_list(_M003_RESULT_STATUSES)}"),
        ("test_results.tested_by (not a user)", "tested_by", "test_results",
         f"tested_by IS NULL OR tested_by NOT IN {users}"),
        ("test_results.sample_id (no such sample)", "sample_id", "test_results",
         "sample_id NOT IN (SELECT sample_id FROM samples)"),
        ("test_results spec_min > spec_max", "id", "test_results",
         "spec_min IS NOT NULL AND spec_max IS NOT NULL AND spec_min > spec_max"),
        ("protocols.sample_type", "sample_type", "protocols",
         f"sample_type NOT IN {_sql_list(_M003_SAMPLE_TYPES)}"),
        ("protocols.created_by (not a user)", "created_by", "protocols",
         f"created_by IS NOT NULL AND created_by NOT IN {users}"),
        ("audit_trail.user (not a user)", "user", "audit_trail", f"user NOT IN {users}"),
    ]
    problems = []
    for label, column, table, where in checks:
        rows = conn.execute(
            f"SELECT {column} AS v, COUNT(*) AS n FROM {table} WHERE {where} GROUP BY 1"
        ).fetchall()
        if rows:
            found = ", ".join(f"{r['v']!r} ×{r['n']}" for r in rows[:10])
            problems.append(f"{label}: {found}")
    return problems


def _m003_constraints(conn):
    """
    Audit M4: CHECK constraints, user foreign keys, created/updated timestamps.
    SQLite can't add constraints to existing tables, so each table is rebuilt.
    Data is validated first; if anything would violate a rule the migration
    stops with a description and changes nothing. Existing rows keep NULL
    timestamps ("not recorded"); new rows default to UTC now. See ADR 0007.
    """
    # 1. Accounts that own automated actions (imports, migrations, simulator).
    for name in _M003_SYSTEM_ACCOUNTS:
        row = conn.execute("SELECT role FROM users WHERE username = ?", (name,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'system')",
                         (name, _UNUSABLE_PASSWORD))
        elif row["role"] != "system":
            raise MigrationError(
                f"Migration 3 needs '{name}' as a non-login system account, but a "
                f"{row['role']} account with that name exists. Rename it first.")

    # 2. Refuse to touch anything if existing data breaks a new rule.
    problems = _m003_problems(conn)
    if problems:
        raise MigrationError(
            "Migration 3 stopped — nothing was changed. These existing values break "
            "the new rules; fix them, then restart:\n  - " + "\n  - ".join(problems))

    # 3. Move the old tables aside (SQLite rewrites their FKs to each other),
    #    create the constrained tables under the real names, copy, drop old.
    tables = ["users", "protocols", "samples", "test_results", "audit_trail"]
    for name in ("idx_samples_status", "idx_samples_priority", "idx_samples_id",
                 "idx_results_sample", "idx_results_status", "idx_audit_timestamp"):
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    for t in tables:
        conn.execute(f"ALTER TABLE {t} RENAME TO {t}_old")

    conn.execute(f"""
        CREATE TABLE users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            role        TEXT NOT NULL CHECK (role IN {_sql_list(_M003_ROLES)})
        )""")
    conn.execute(f"""
        CREATE TABLE protocols (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            sample_type TEXT NOT NULL CHECK (sample_type IN {_sql_list(_M003_SAMPLE_TYPES)}),
            description TEXT,
            steps       TEXT,
            created_by  TEXT REFERENCES users(username),
            created_at  TEXT DEFAULT {_UTC_NOW}
        )""")
    conn.execute(f"""
        CREATE TABLE samples (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id         TEXT UNIQUE NOT NULL,
            product_name      TEXT NOT NULL,
            lot_number        TEXT,
            manufacturer      TEXT,
            sample_type       TEXT CHECK (sample_type IN {_sql_list(_M003_SAMPLE_TYPES)}),
            recall_class      TEXT CHECK (recall_class IN {_sql_list(_M003_CLASSES)}),
            priority          TEXT CHECK (priority IN {_sql_list(_M003_PRIORITIES)}),
            reason_for_recall TEXT,
            collection_date   TEXT,
            status            TEXT NOT NULL DEFAULT 'Pending'
                              CHECK (status IN {_sql_list(_M003_STATUSES)}),
            assigned_to       TEXT REFERENCES users(username),
            protocol_id       INTEGER REFERENCES protocols(id),
            notes             TEXT,
            source            TEXT NOT NULL DEFAULT 'Manual'
                              CHECK (source IN {_sql_list(_M003_SOURCES)}),
            is_simulated      INTEGER NOT NULL DEFAULT 0 CHECK (is_simulated IN (0, 1)),
            version           INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
            created_at        TEXT DEFAULT {_UTC_NOW},
            updated_at        TEXT DEFAULT {_UTC_NOW}
        )""")
    conn.execute(f"""
        CREATE TABLE test_results (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id    TEXT NOT NULL REFERENCES samples(sample_id),
            test_name    TEXT NOT NULL,
            result_value REAL,
            result_unit  TEXT,
            spec_min     REAL,
            spec_max     REAL,
            status       TEXT NOT NULL CHECK (status IN {_sql_list(_M003_RESULT_STATUSES)}),
            tested_by    TEXT NOT NULL REFERENCES users(username),
            tested_at    TEXT,
            notes        TEXT,
            is_simulated INTEGER NOT NULL DEFAULT 0 CHECK (is_simulated IN (0, 1)),
            created_at   TEXT DEFAULT {_UTC_NOW},
            CHECK (spec_min IS NULL OR spec_max IS NULL OR spec_min <= spec_max)
        )""")
    conn.execute("""
        CREATE TABLE audit_trail (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user      TEXT NOT NULL REFERENCES users(username),
            action    TEXT NOT NULL,
            module    TEXT NOT NULL,
            target_id TEXT,
            detail    TEXT
        )""")

    copies = {
        "users": "id, username, password, role",
        "protocols": "id, name, sample_type, description, steps, created_by, created_at",
        "audit_trail": "id, timestamp, user, action, module, target_id, detail",
    }
    for t, cols in copies.items():
        conn.execute(f"INSERT INTO {t} ({cols}) SELECT {cols} FROM {t}_old")
    conn.execute("""
        INSERT INTO samples (id, sample_id, product_name, lot_number, manufacturer,
            sample_type, recall_class, priority, reason_for_recall, collection_date,
            status, assigned_to, protocol_id, notes, source, is_simulated, version,
            created_at, updated_at)
        SELECT id, sample_id, product_name, lot_number, manufacturer,
            sample_type, recall_class, priority, reason_for_recall, collection_date,
            status, assigned_to, protocol_id, notes, source, is_simulated, version,
            NULL, NULL
        FROM samples_old""")
    conn.execute("""
        INSERT INTO test_results (id, sample_id, test_name, result_value, result_unit,
            spec_min, spec_max, status, tested_by, tested_at, notes, is_simulated, created_at)
        SELECT id, sample_id, test_name, result_value, result_unit,
            spec_min, spec_max, status, tested_by, tested_at, notes, is_simulated, NULL
        FROM test_results_old""")

    for t in ["test_results", "samples", "audit_trail", "protocols", "users"]:  # children first
        conn.execute(f"DROP TABLE {t}_old")

    # idx_samples_id is not recreated: UNIQUE(sample_id) already indexes it.
    conn.execute("CREATE INDEX idx_samples_status   ON samples(status)")
    conn.execute("CREATE INDEX idx_samples_priority ON samples(priority)")
    conn.execute("CREATE INDEX idx_results_sample   ON test_results(sample_id)")
    conn.execute("CREATE INDEX idx_results_status   ON test_results(status)")
    conn.execute("CREATE INDEX idx_audit_timestamp  ON audit_trail(timestamp)")

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise MigrationError(f"Migration 3: foreign key check failed: {violations[:10]}")


def _m004_audit_trail(conn):
    """
    Audit C3: structured change records and an append-only trail (ADR 0008).
    Adds old_value / new_value / reason, and triggers that make any UPDATE or
    DELETE on audit_trail fail. Existing rows are left exactly as they are.
    A later migration that must rebuild audit_trail has to drop and recreate
    these triggers inside its own transaction.
    """
    for column in ("old_value", "new_value", "reason"):
        conn.execute(f"ALTER TABLE audit_trail ADD COLUMN {column} TEXT")
    for event in ("UPDATE", "DELETE"):
        conn.execute(f"""
            CREATE TRIGGER audit_trail_no_{event.lower()}
            BEFORE {event} ON audit_trail
            BEGIN
                SELECT RAISE(ABORT, 'audit_trail is append-only');
            END""")


# Dosage forms a specification can target, frozen as of migration 5.
_M005_SAMPLE_TYPES = ("Tablet", "Capsule", "Injectable", "Liquid", "Topical", "Powder")


def _m005_specifications(conn):
    """
    Audit H4d: specification master data, one row per sample type × test
    (ADR 0012). Results gain spec_id/spec_version recording which spec they
    were evaluated against; existing results keep NULL ("as recorded").
    """
    conn.execute(f"""
        CREATE TABLE specifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_type TEXT NOT NULL CHECK (sample_type IN {_sql_list(_M005_SAMPLE_TYPES)}),
            test_name   TEXT NOT NULL,
            spec_min    REAL,
            spec_max    REAL,
            unit        TEXT NOT NULL,
            version     INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
            updated_by  TEXT NOT NULL REFERENCES users(username),
            updated_at  TEXT NOT NULL DEFAULT {_UTC_NOW},
            UNIQUE (sample_type, test_name),
            CHECK (spec_min IS NOT NULL OR spec_max IS NOT NULL),
            CHECK (spec_min IS NULL OR spec_max IS NULL OR spec_min <= spec_max)
        )""")
    conn.execute("ALTER TABLE test_results ADD COLUMN spec_id INTEGER REFERENCES specifications(id)")
    conn.execute("ALTER TABLE test_results ADD COLUMN spec_version INTEGER")


def _m006_password_security(conn):
    """
    Audit H6: lockout state per account, and no unsalted SHA-256 hash left
    at rest — each is wrapped in scrypt (scrypt-sha256$...) and upgraded to
    plain scrypt at the user's next sign-in (ADR 0013).
    """
    conn.execute("ALTER TABLE users ADD COLUMN failed_logins INTEGER NOT NULL DEFAULT 0 "
                 "CHECK (failed_logins >= 0)")
    conn.execute("ALTER TABLE users ADD COLUMN locked_until TEXT")
    legacy = conn.execute(
        "SELECT username, password FROM users WHERE length(password) = 64 "
        "AND password NOT GLOB '*[^0-9a-f]*'").fetchall()
    for username, digest in legacy:
        conn.execute("UPDATE users SET password = ? WHERE username = ?",
                     (passwords.wrap_legacy(digest), username))


def _m007_result_signatures(conn):
    """
    Audit 3.3: second-person review with e-signature (ADR 0014). One
    signature per result, append-only, never by the analyst who logged it.
    Existing results have none, so they show as awaiting review.
    """
    conn.execute(f"""
        CREATE TABLE result_signatures (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER NOT NULL UNIQUE REFERENCES test_results(id),
            signed_by TEXT NOT NULL REFERENCES users(username),
            meaning   TEXT NOT NULL CHECK (meaning IN ('Approved', 'Rejected')),
            reason    TEXT,
            signed_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            CHECK (meaning = 'Approved' OR length(trim(coalesce(reason, ''))) > 0)
        )""")
    conn.execute("""
        CREATE TRIGGER result_signatures_second_person
        BEFORE INSERT ON result_signatures
        WHEN NEW.signed_by = (SELECT tested_by FROM test_results WHERE id = NEW.result_id)
        BEGIN
            SELECT RAISE(ABORT, 'a result must be signed by someone other than its analyst');
        END""")
    for event in ("UPDATE", "DELETE"):
        conn.execute(f"""
            CREATE TRIGGER result_signatures_no_{event.lower()}
            BEFORE {event} ON result_signatures
            BEGIN
                SELECT RAISE(ABORT, 'result_signatures is append-only');
            END""")


def _m008_oos_investigations(conn):
    """
    Audit 3.4: an investigation per OOS result (ADR 0015). Never deleted;
    once Closed, never changed; not closed by the result's own analyst.
    Unsigned OOS results on In Progress samples get one opened by `system`;
    OOS results on other samples stay as recorded.
    """
    conn.execute(f"""
        CREATE TABLE oos_investigations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id  INTEGER NOT NULL UNIQUE REFERENCES test_results(id),
            opened_by  TEXT NOT NULL REFERENCES users(username),
            opened_at  TEXT NOT NULL DEFAULT {_UTC_NOW},
            status     TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open', 'Closed')),
            conclusion TEXT CHECK (conclusion IN ('Assignable laboratory error', 'OOS confirmed')),
            findings   TEXT,
            closed_by  TEXT REFERENCES users(username),
            closed_at  TEXT,
            CHECK ((status = 'Open' AND conclusion IS NULL AND closed_by IS NULL
                    AND closed_at IS NULL)
                OR (status = 'Closed' AND conclusion IS NOT NULL AND closed_by IS NOT NULL
                    AND closed_at IS NOT NULL AND length(trim(coalesce(findings, ''))) > 0))
        )""")
    guards = {
        "no_delete": ("BEFORE DELETE", "", "oos_investigations rows are never deleted"),
        "closed_is_final": ("BEFORE UPDATE", "WHEN OLD.status = 'Closed'",
                            "a closed investigation cannot be changed"),
        "fixed_origin": ("BEFORE UPDATE",
                         "WHEN NEW.result_id IS NOT OLD.result_id OR NEW.opened_by IS NOT "
                         "OLD.opened_by OR NEW.opened_at IS NOT OLD.opened_at",
                         "the result and opening of an investigation cannot be changed"),
        "independent_close": ("BEFORE UPDATE",
                              "WHEN NEW.closed_by = (SELECT tested_by FROM test_results "
                              "WHERE id = NEW.result_id)",
                              "an investigation must be closed by someone other than the analyst"),
    }
    for name, (event, when, message) in guards.items():
        conn.execute(f"""
            CREATE TRIGGER oos_investigations_{name}
            {event} ON oos_investigations {when}
            BEGIN
                SELECT RAISE(ABORT, '{message}');
            END""")
    conn.execute("""
        INSERT INTO oos_investigations (result_id, opened_by)
        SELECT r.id, 'system' FROM test_results r
        JOIN samples s ON s.sample_id = r.sample_id
        LEFT JOIN result_signatures g ON g.result_id = r.id
        WHERE r.status = 'Fail (OOS)' AND s.status = 'In Progress' AND g.id IS NULL
        ORDER BY r.id""")


def _m009_user_management(conn):
    """
    Audit 3.6: accounts can be disabled (never deleted: results, signatures
    and the audit trail refer to them), and a password set by an admin must
    be changed at the next sign-in (ADR 0017). Existing accounts stay active
    and keep their passwords.
    """
    conn.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1 "
                 "CHECK (active IN (0, 1))")
    conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL "
                 "DEFAULT 0 CHECK (must_change_password IN (0, 1))")


MIGRATIONS = [
    _m001_simulated_flag,
    _m002_sample_version,
    _m003_constraints,
    _m004_audit_trail,
    _m005_specifications,
    _m006_password_security,
    _m007_result_signatures,
    _m008_oos_investigations,
    _m009_user_management,
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
