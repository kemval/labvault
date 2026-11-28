"""Migration 3: CHECK constraints, user foreign keys, timestamps (audit M4, ADR 0007)."""
import sqlite3

import pytest

import services
from fake_fda import record, serve
from repo import core, schema, users
from conftest import insert_legacy_result
from repo.results import insert_test_result
from repo.samples import insert_sample
import test_services
from test_services import BASE, rows

SAMPLE = {**BASE, "sample_id": "S-1", "status": "Pending", "source": "Manual"}
RESULT = {"sample_id": "S-1", "test_name": "Potency (% Label Claim)", "result_value": 95.0,
          "result_unit": "%", "spec_min": 90.0, "spec_max": 110.0, "status": "Pass",
          "tested_by": "kembly", "tested_at": "2024-01-02", "notes": ""}


def execute(sql, params=()):
    conn = core.get_conn()
    try:
        with conn:
            conn.execute(sql, params)
    finally:
        conn.close()


# ── value rules ──────────────────────────────────────────────

@pytest.mark.parametrize("field, bad", [
    ("status", "Done"), ("priority", "Urgent"), ("recall_class", "Class IV"),
    ("sample_type", "Gel"), ("source", "Email"), ("status", None),
])
def test_sample_rejects_invalid_values(lab_db, field, bad):
    with pytest.raises(sqlite3.IntegrityError):
        insert_sample({**SAMPLE, field: bad})


@pytest.mark.parametrize("sql", [
    "UPDATE samples SET is_simulated = 2",
    "UPDATE samples SET version = 0",
])
def test_sample_rejects_invalid_flags(lab_db, sql):
    insert_sample(SAMPLE)
    with pytest.raises(sqlite3.IntegrityError):
        execute(sql)


@pytest.mark.parametrize("change", [
    {"status": "Maybe"}, {"status": None}, {"spec_min": 110.0, "spec_max": 90.0},
    {"tested_by": None},
])
def test_result_rejects_invalid_values(lab_db, change):
    insert_sample(SAMPLE)
    with pytest.raises(sqlite3.IntegrityError):
        insert_test_result({**RESULT, **change})


def test_user_role_is_checked(lab_db):
    with pytest.raises(sqlite3.IntegrityError):
        execute("INSERT INTO users (username, password, role) VALUES ('x', 'h', 'superuser')")


# ── user references ──────────────────────────────────────────

@pytest.mark.parametrize("write", [
    lambda: insert_sample({**SAMPLE, "assigned_to": "nobody"}),
    lambda: (insert_sample(SAMPLE), insert_test_result({**RESULT, "tested_by": "nobody"})),
    lambda: services.log_event("nobody", "REPORT_EXPORTED", "Reports"),
    lambda: services.create_protocol({"name": "P", "sample_type": "Tablet",
                                      "description": "", "steps": ""}, "nobody"),
])
def test_writes_must_name_a_real_account(lab_db, write):
    with pytest.raises(sqlite3.IntegrityError):
        write()


def test_unassigned_sample_is_allowed(lab_db):
    sample_id = services.register_sample({**BASE, "assigned_to": None}, "admin")
    assert rows("SELECT assigned_to FROM samples WHERE sample_id = ?", (sample_id,)) == \
        [{"assigned_to": None}]


def test_referenced_user_cannot_be_deleted(lab_db):
    services.register_sample(BASE, "admin")          # assigned to kembly, audited as admin
    for name in ("kembly", "admin"):
        with pytest.raises(sqlite3.IntegrityError):
            execute("DELETE FROM users WHERE username = ?", (name,))


# ── system accounts ──────────────────────────────────────────

def test_system_accounts_exist_and_cannot_log_in(lab_db):
    accounts = {r["username"]: r["role"] for r in rows("SELECT * FROM users")}
    assert accounts["system"] == accounts["simulator"] == "system"
    # Even if someone set a known password on one, the role blocks login.
    execute("UPDATE users SET password = ? WHERE username = 'system'", (users.hash_pw("pw"),))
    assert users.authenticate("system", "pw") is None
    assert users.authenticate("kembly", "lab2024") is not None


def test_system_accounts_are_not_lab_techs(lab_db):
    assert sorted(users.lab_techs()) == ["carlos", "kembly", "maria"]


def test_secure_instance_without_techs_imports_unassigned(fresh_db, settings, monkeypatch):
    settings(admin_password="a-long-admin-password")
    users.seed_users(demo=False, admin_password="a-long-admin-password")
    serve(monkeypatch, [record(1)])
    assert services.import_fda(limit=1)["count"] == 1
    assert rows("SELECT DISTINCT assigned_to FROM samples") == [{"assigned_to": None}]
    assert rows("SELECT DISTINCT tested_by FROM test_results") == [{"tested_by": "simulator"}]


def test_import_skips_records_the_schema_rejects(lab_db, monkeypatch):
    unclassified = {**record(2), "classification": "Not Yet Classified"}
    serve(monkeypatch, [record(1), unclassified])
    result = services.import_fda(limit=2)
    assert (result["count"], result["already_present"], result["skipped"]) == (1, 0, 1)
    assert [r["sample_id"] for r in rows("SELECT sample_id FROM samples")] == ["D-0001-2024"]
    assert {r["sample_id"] for r in rows("SELECT sample_id FROM test_results")} == {"D-0001-2024"}


def test_register_sample_reports_invalid_values_instead_of_retrying(lab_db):
    with pytest.raises(sqlite3.IntegrityError):
        services.register_sample({**BASE, "priority": "Urgent"}, "admin")
    assert rows("SELECT * FROM samples") == []


# ── timestamps ───────────────────────────────────────────────

def test_new_rows_get_utc_timestamps_and_updates_bump_updated_at(lab_db):
    sample_id = services.register_sample(BASE, "admin")
    execute("UPDATE samples SET updated_at = '2000-01-01T00:00:00Z'")
    services.update_sample(sample_id, 1, "admin", status="In Progress", reason="test")
    [s] = rows("SELECT created_at, updated_at FROM samples")
    assert s["created_at"].endswith("Z") and len(s["created_at"]) == 20
    assert s["updated_at"] > "2000-01-01T00:00:00Z"
    services.record_result({**test_services.RESULT, "sample_id": sample_id}, "kembly")
    [r] = rows("SELECT created_at FROM test_results")
    assert r["created_at"].endswith("Z")


# ── migrating existing databases ─────────────────────────────

@pytest.fixture
def v2_db(tmp_path, monkeypatch):
    """A database at schema version 2 (before migration 3), with demo data."""
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "v2.db"))
    with monkeypatch.context() as m:
        m.setattr(schema, "MIGRATIONS", schema.MIGRATIONS[:2])
        schema.init_db()
        users.seed_users(demo=True)
        insert_sample(SAMPLE)
        insert_legacy_result(RESULT)
        execute("INSERT INTO audit_trail (timestamp, user, action, module) "
                "VALUES ('2024-01-01 00:00:00', 'system', 'SAMPLE_IMPORTED', 'FDA Seed')")
    assert schema.schema_version(core.get_conn()) == 2
    return core.DB_PATH


def snapshot(path):
    conn = sqlite3.connect(path)
    try:
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY id").fetchall()
                for t in ("users", "samples", "test_results", "audit_trail", "protocols")}
    finally:
        conn.close()


def test_migration_keeps_every_row_and_leaves_old_timestamps_empty(v2_db):
    before = snapshot(v2_db)
    schema.apply_migrations()
    after = snapshot(v2_db)

    assert schema.schema_version(core.get_conn()) == len(schema.MIGRATIONS)
    # Same rows and ids; samples/results gain NULL timestamps; users gain the
    # two system accounts (the 'system' audit row now references one).
    assert [r[:-2] for r in after["samples"]] == before["samples"]
    assert {r[-2:] for r in after["samples"]} == {(None, None)}
    width = len(before["test_results"][0])
    assert [r[:width] for r in after["test_results"]] == before["test_results"]
    # + created_at (migration 3), spec_id and spec_version (migration 5): all empty
    assert {r[width:] for r in after["test_results"]} == {(None, None, None)}
    assert [r[:7] for r in after["audit_trail"]] == before["audit_trail"]   # + 3 new columns
    assert after["users"][:len(before["users"])] == before["users"]
    assert {r[1] for r in after["users"][len(before["users"]):]} == {"system", "simulator"}
    assert rows("PRAGMA foreign_key_check") == []
    assert {r["name"] for r in rows("SELECT name FROM sqlite_master")} >= {
        "idx_samples_status", "idx_results_sample", "idx_audit_timestamp"}


@pytest.mark.parametrize("bad_sql, reported", [
    ("UPDATE samples SET status = 'Archived'", "samples.status: 'Archived'"),
    ("UPDATE samples SET assigned_to = 'ghost'", "samples.assigned_to (not a user): 'ghost'"),
    ("UPDATE test_results SET tested_by = 'ghost'", "test_results.tested_by (not a user)"),
    ("UPDATE audit_trail SET user = 'ghost'", "audit_trail.user (not a user): 'ghost'"),
])
def test_migration_with_bad_data_stops_and_changes_nothing(v2_db, bad_sql, reported):
    conn = sqlite3.connect(v2_db)          # no FK enforcement, like old app versions
    with conn:
        conn.execute(bad_sql)
    conn.close()
    before = snapshot(v2_db)

    with pytest.raises(schema.MigrationError) as e:
        schema.apply_migrations()

    assert reported in str(e.value) and "nothing was changed" in str(e.value)
    assert snapshot(v2_db) == before                  # not even the system accounts
    assert schema.schema_version(core.get_conn()) == 2
    assert not [r for r in rows("SELECT name FROM sqlite_master") if r["name"].endswith("_old")]


def test_migration_refuses_a_human_account_named_system(v2_db):
    execute("INSERT INTO users (username, password, role) VALUES ('simulator', 'h', 'lab_tech')")
    with pytest.raises(schema.MigrationError, match="'simulator'.*lab_tech"):
        schema.apply_migrations()
    assert schema.schema_version(core.get_conn()) == 2

