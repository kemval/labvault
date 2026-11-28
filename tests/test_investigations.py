"""OOS investigations (audit 3.4, migration 8, ADR 0015)."""
import sqlite3

import pytest

import services
from domain import MAX_FAILED_LOGINS
from fake_fda import record, serve
from repo import core, schema, users
from repo.results import insert_test_result
from repo.samples import insert_sample
from test_app_login import login, run_app
from test_result_entry import log
from test_services import BASE, audit, rows

LAB_ERROR, CONFIRMED = "Assignable laboratory error", "OOS confirmed"
POTENCY = "Potency (% Label Claim)"


def close(inv, conclusion=LAB_ERROR, user="admin", password="admin123",
          findings="Dilution error found in worksheet"):
    return services.close_investigation(inv, user, password, conclusion, findings)


def sign(result_id, meaning, reason="per investigation"):
    return services.sign_result(result_id, "carlos", "lab2024", meaning, reason)


def sql(statement, params=()):
    with core.transaction() as conn:
        conn.execute(statement, params)


@pytest.fixture
def oos(open_sample):
    """kembly's OOS potency result (80 %) and its investigation."""
    return log(open_sample, POTENCY, 80.0)


# ── opening ──────────────────────────────────────────────────

def test_an_oos_result_opens_an_investigation(oos):
    [inv] = rows("SELECT * FROM oos_investigations")
    assert (inv["id"], inv["result_id"], inv["opened_by"], inv["status"]) == \
        (oos["investigation_id"], oos["id"], "kembly", "Open")
    assert audit("OOS_INVESTIGATION_OPENED")[0]["new_value"] == "Open"


def test_a_pass_opens_none(open_sample):
    assert log(open_sample, POTENCY, 100.0)["investigation_id"] is None
    assert rows("SELECT * FROM oos_investigations") == []


def test_fda_import_opens_investigations_for_in_progress_oos_only(fresh_db, monkeypatch):
    fresh_db.seed_users(demo=True)
    serve(monkeypatch, [record(1, "Subpotent", "Ongoing"), record(2, "Subpotent", "Completed")])
    services.import_fda(limit=2)
    opened = rows("""SELECT s.status FROM oos_investigations i
                     JOIN test_results r ON r.id = i.result_id
                     JOIN samples s ON s.sample_id = r.sample_id""")
    in_progress_oos = rows("""SELECT COUNT(*) AS n FROM test_results r JOIN samples s
                              USING (sample_id) WHERE r.status = 'Fail (OOS)'
                              AND s.status = 'In Progress'""")[0]["n"]
    assert len(opened) == in_progress_oos and {o["status"] for o in opened} <= {"In Progress"}


def test_migration_8_backfills_unsigned_oos_on_in_progress_samples(tmp_path, monkeypatch):
    all_migrations = schema.MIGRATIONS
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "v7.db"))
    monkeypatch.setattr(schema, "MIGRATIONS", all_migrations[:7])
    schema.init_db()
    users.seed_users(demo=True)
    for sid, status in (("WIP", "In Progress"), ("DONE", "Completed")):
        insert_sample({**BASE, "sample_id": sid, "status": status, "source": "Manual"})
        for value, result_status in ((80.0, "Fail (OOS)"), (100.0, "Pass")):
            insert_test_result({"sample_id": sid, "test_name": POTENCY, "result_value": value,
                                "result_unit": "%", "spec_min": 90.0, "spec_max": 110.0,
                                "status": result_status, "tested_by": "kembly",
                                "tested_at": "2026-01-02", "notes": ""})
    schema.apply_migrations(all_migrations)             # → v8
    assert rows("""SELECT r.sample_id, i.opened_by, i.status FROM oos_investigations i
                   JOIN test_results r ON r.id = i.result_id""") == [
        {"sample_id": "WIP", "opened_by": "system", "status": "Open"}]


# ── an OOS can't be signed until QA concludes ───────────────

def test_open_investigation_blocks_signing(oos):
    for meaning in ("Approved", "Rejected"):
        with pytest.raises(services.PermissionDeniedError, match="open investigation"):
            sign(oos["id"], meaning)


@pytest.mark.parametrize("conclusion, allowed, refused", [
    (LAB_ERROR, "Rejected", "Approved"),     # invalid result: only rejected, then retest
    (CONFIRMED, "Approved", "Rejected"),     # valid failure: can't be thrown out
])
def test_conclusion_decides_the_signature(oos, conclusion, allowed, refused):
    close(oos["investigation_id"], conclusion)
    with pytest.raises(services.PermissionDeniedError, match=f"only be signed as {allowed}"):
        sign(oos["id"], refused)
    assert sign(oos["id"], allowed)["meaning"] == allowed


def test_confirmed_oos_is_approved_and_the_sample_completes_failing(open_sample, oos):
    close(oos["investigation_id"], CONFIRMED, findings="No lab error; batch is subpotent")
    sign(oos["id"], "Approved")
    assert services.update_sample(open_sample, 2, "kembly", status="Completed", reason="done")
    assert rows("SELECT status FROM test_results") == [{"status": "Fail (OOS)"}]


# ── closing ──────────────────────────────────────────────────

def test_close_is_recorded_and_audited(oos):
    saved = close(oos["investigation_id"])
    [inv] = rows("SELECT * FROM oos_investigations")
    assert (inv["status"], inv["conclusion"], inv["closed_by"], inv["closed_at"]) == \
        ("Closed", LAB_ERROR, "admin", saved["closed_at"])
    [entry] = audit("OOS_INVESTIGATION_CLOSED")
    assert (entry["old_value"], entry["new_value"], entry["reason"]) == \
        ("Open", LAB_ERROR, "Dilution error found in worksheet")


def test_only_admins_close(oos):
    with pytest.raises(services.PermissionDeniedError, match="Only an admin"):
        close(oos["investigation_id"], user="carlos", password="lab2024")


def test_admin_cannot_close_on_own_result(open_sample):
    own = services.record_result({"sample_id": open_sample, "test_name": POTENCY,
                                  "result_value": 80.0, "tested_at": "2026-01-02"}, "admin")
    with pytest.raises(services.PermissionDeniedError, match="another admin"):
        close(own["investigation_id"])


def test_closed_is_final(oos):
    close(oos["investigation_id"])
    with pytest.raises(services.PermissionDeniedError, match="already closed"):
        close(oos["investigation_id"], CONFIRMED)


@pytest.mark.parametrize("conclusion, findings, error", [
    (LAB_ERROR, "  ", "findings"),
    ("Probably fine", "x", "Unknown conclusion"),
])
def test_close_needs_a_conclusion_and_findings(oos, conclusion, findings, error):
    with pytest.raises(services.ServiceError, match=error):
        close(oos["investigation_id"], conclusion, findings=findings)


def test_wrong_password_keeps_it_open_and_counts_toward_lockout(oos):
    for _ in range(MAX_FAILED_LOGINS):
        with pytest.raises(services.SignatureError, match="still open"):
            close(oos["investigation_id"], password="wrong")
    assert rows("SELECT status FROM oos_investigations") == [{"status": "Open"}]
    assert audit("SIGNATURE_FAILED")[0]["module"] == "OOS Investigations"
    assert audit("ACCOUNT_LOCKED")[0]["user"] == "admin"


# ── the database guards ──────────────────────────────────────

def test_database_guards_investigations(oos):
    inv = oos["investigation_id"]
    guarded = [
        ("DELETE FROM oos_investigations", "never deleted"),
        ("UPDATE oos_investigations SET opened_by = 'admin'", "cannot be changed"),
        ("UPDATE oos_investigations SET status = 'Closed', conclusion = 'OOS confirmed', "
         "findings = 'x', closed_by = 'kembly', closed_at = 'now'", "other than the analyst"),
        ("UPDATE oos_investigations SET status = 'Closed', conclusion = 'OOS confirmed', "
         "closed_by = 'admin', closed_at = 'now'", "CHECK"),             # no findings
    ]
    for statement, error in guarded:
        with pytest.raises(sqlite3.IntegrityError, match=error):
            sql(statement)
    close(inv)
    with pytest.raises(sqlite3.IntegrityError, match="closed investigation cannot be changed"):
        sql("UPDATE oos_investigations SET conclusion = 'OOS confirmed'")


# ── the pages ────────────────────────────────────────────────

def open_page(username, password, page="🔎  OOS Investigations"):
    at = login(run_app(), username, password)
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, at.exception
    return at


def test_admin_closes_on_the_page(oos, settings):
    settings(demo="true")
    at = open_page("admin", "admin123")
    next(r for r in at.radio if r.label.startswith("Conclusion")).set_value(CONFIRMED)
    next(w for w in at.text_area if w.label.startswith("Findings")).input("Retest confirmed")
    next(w for w in at.text_input if w.label.startswith("Your password")).input("admin123")
    next(b for b in at.button if b.label == "Close investigation").click().run()
    assert not at.exception, at.exception
    assert rows("SELECT status, conclusion FROM oos_investigations") == [
        {"status": "Closed", "conclusion": CONFIRMED}]
    assert any("Closed investigation" in s.value for s in at.success)


def test_lab_tech_sees_investigations_read_only(oos, settings):
    settings(demo="true")
    at = open_page("carlos", "lab2024")
    assert len(at.dataframe[0].value) == 1
    assert not [b for b in at.button if b.label == "Close investigation"]
    assert any("Only an admin" in c.value for c in at.caption)


def test_review_tab_offers_only_the_concluded_meaning(oos, settings):
    settings(demo="true")
    close(oos["investigation_id"], LAB_ERROR)
    at = open_page("carlos", "lab2024", "📋  Test Results")
    meaning = next(r for r in at.radio if r.label.startswith("Meaning"))
    assert list(meaning.options) == ["Reviewed and rejected — the result is invalid; "
                                     "a retest is needed"]
    assert any("can only be signed as Rejected" in w.value for w in at.warning)
