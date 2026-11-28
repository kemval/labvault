"""Audit-trail completeness (audit C3 b–h, migration 4, ADR 0008)."""
import re
import sqlite3

import pytest

import services
from repo import audit as audit_repo, core, schema
from test_app_login import login, run_app
from test_services import BASE, audit, rows

UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


# ── append-only ──────────────────────────────────────────────

@pytest.mark.parametrize("sql", [
    "UPDATE audit_trail SET detail = 'edited'",
    "DELETE FROM audit_trail",
])
def test_audit_rows_cannot_be_changed_or_deleted(lab_db, sql):
    services.log_event("admin", "REPORT_EXPORTED", "Reports", "", "original")
    conn = sqlite3.connect(lab_db.DB_PATH)       # raw connection, as a script would use
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            with conn:
                conn.execute(sql)
    finally:
        conn.close()
    assert [r["detail"] for r in audit()] == ["original"]


def test_migration_4_adds_columns_and_triggers(lab_db):
    assert schema.schema_version(core.get_conn()) == len(schema.MIGRATIONS) == 4
    columns = {r["name"] for r in rows("PRAGMA table_info(audit_trail)")}
    assert {"old_value", "new_value", "reason"} <= columns
    triggers = {r["name"] for r in rows("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert triggers == {"audit_trail_no_update", "audit_trail_no_delete"}


# ── structured changes with a reason ─────────────────────────

def test_change_records_old_value_new_value_and_reason(lab_db):
    sample_id = services.register_sample(BASE, "admin")
    services.update_sample(sample_id, 1, "admin", status="In Progress", assigned_to=None,
                           reason="  Started HPLC run  ")
    services.update_sample(sample_id, 2, "admin", assigned_to="maria", reason="Workload")
    status = audit("STATUS_UPDATED")
    assign = audit("SAMPLE_ASSIGNED")
    assert [(a["old_value"], a["new_value"], a["reason"]) for a in status] == \
        [("Pending", "In Progress", "Started HPLC run")]
    assert [(a["old_value"], a["new_value"], a["reason"]) for a in assign] == \
        [("kembly", "maria", "Workload")]
    assert all(UTC.match(a["timestamp"]) for a in status + assign + audit("SAMPLE_CREATED"))


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_change_without_reason_is_refused_and_writes_nothing(lab_db, reason):
    sample_id = services.register_sample(BASE, "admin")
    with pytest.raises(services.ServiceError, match="reason"):
        services.update_sample(sample_id, 1, "admin", status="Rejected", reason=reason)
    assert rows("SELECT status, version FROM samples") == [{"status": "Pending", "version": 1}]
    assert audit("STATUS_UPDATED") == []


def test_saving_without_changes_needs_no_reason(lab_db):
    sample_id = services.register_sample(BASE, "admin")
    assert services.update_sample(sample_id, 1, "carlos", status="Pending") is False


def test_tracking_page_requires_a_reason(lab_db, settings):
    settings(demo="true")
    sample_id = services.register_sample(BASE, "admin")
    at = login(run_app(), "kembly", "lab2024")
    at.sidebar.radio[0].set_value("🔬  Sample Tracking").run()
    at.selectbox(key=f"status_{sample_id}").set_value("In Progress")
    at.button(key=f"save_{sample_id}").click().run()
    assert any("reason" in e.value for e in at.error)
    assert rows("SELECT status FROM samples") == [{"status": "Pending"}]


# ── sign-in events ───────────────────────────────────────────

def test_sign_in_success_and_failures_are_audited(lab_db):
    assert services.sign_in("kembly", "lab2024")["username"] == "kembly"
    assert services.sign_in("kembly", "wrong") is None          # real account
    assert services.sign_in("mallory", "x") is None              # no such account
    assert services.sign_in("system", "!") is None               # system account
    events = [(a["user"], a["action"], a["target_id"]) for a in audit()]
    assert events == [
        ("kembly", "LOGIN", "kembly"),
        ("kembly", "LOGIN_FAILED", "kembly"),
        ("system", "LOGIN_FAILED", "mallory"),
        ("system", "LOGIN_FAILED", "system"),
    ]


def test_attempted_username_is_truncated(lab_db):
    services.sign_in("x" * 5000, "pw")
    [row] = audit("LOGIN_FAILED")
    assert len(row["target_id"]) == 64


def test_app_sign_in_and_sign_out_are_audited(lab_db, settings):
    settings(demo="true")
    services.register_sample(BASE, "admin")        # skip the first-run import
    at = login(run_app(), "maria", "lab2024")
    at.sidebar.button[-1].click().run()            # Sign Out
    assert [(a["user"], a["action"]) for a in audit() if a["module"] == "Auth"] == \
        [("maria", "LOGIN"), ("maria", "LOGOUT")]


def test_dashboard_feed_leaves_out_sign_in_events(lab_db, settings):
    settings(demo="true")
    services.register_sample(BASE, "admin")
    at = login(run_app(), "maria", "lab2024")
    feed = " ".join(str(m.value) for m in at.markdown)
    assert "Registered: Metformin" in feed
    assert "Signed in" not in feed


# ── exports are audited on download ──────────────────────────

def test_generating_a_report_writes_no_audit_row(lab_db, settings):
    settings(demo="true")
    services.register_sample(BASE, "admin")
    at = login(run_app(), "admin", "admin123")
    at.sidebar.radio[0].set_value("📈  Reports").run()
    next(b for b in at.button if "Generate Excel" in b.label).click().run()
    assert not at.exception, at.exception
    assert audit("REPORT_EXPORTED") == []


def test_download_callback_audits_the_export(lab_db):
    from views.reports import _log_download
    _log_download("admin", "Excel: 1 samples, 0 results")
    [row] = audit("REPORT_EXPORTED")
    assert (row["user"], row["detail"]) == ("admin", "Downloaded Excel: 1 samples, 0 results")


# ── the whole trail is reachable ─────────────────────────────

@pytest.fixture
def busy_trail(lab_db):
    with core.transaction() as conn:
        for i in range(250):
            audit_repo.write_audit(conn, "carlos" if i % 2 else "maria",
                                   "REPORT_EXPORTED", "Reports", str(i), f"entry {i}")
    return lab_db


def test_search_pages_through_everything_newest_first(busy_trail):
    first, total = audit_repo.search_audit(limit=100, offset=0)
    last, _ = audit_repo.search_audit(limit=100, offset=200)
    assert total == 250 and len(last) == 50
    assert first[0]["target_id"] == "249" and last[-1]["target_id"] == "0"


def test_search_filters_in_sql(busy_trail):
    _, carlos = audit_repo.search_audit(user="CARL")
    _, none = audit_repo.search_audit(user="%")       # not a wildcard
    _, exports = audit_repo.search_audit(action="REPORT_EXPORTED")
    assert (carlos, none, exports) == (125, 0, 250)
    assert audit_repo.audit_actions() == ["REPORT_EXPORTED"]


def test_audit_page_reaches_old_entries(busy_trail, settings):
    settings(demo="true")
    services.register_sample(BASE, "admin")
    at = login(run_app(), "admin", "admin123")
    at.sidebar.radio[0].set_value("🕵️  Audit Trail").run()
    assert not at.exception, at.exception
    at.number_input(key="audit_page").set_value(3).run()
    targets = set(at.dataframe[0].value["Target"])
    assert "0" in targets and "249" not in targets
    assert "LOGIN" in at.selectbox[0].options      # actions come from the data
