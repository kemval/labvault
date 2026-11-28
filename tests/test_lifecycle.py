"""Sample lifecycle and permission rules (audit H5, ADR 0011)."""
import pytest

import domain
import services
from domain import (STATUS_COMPLETED as DONE, STATUS_IN_PROGRESS as WIP,
                    STATUS_PENDING as PENDING, STATUS_REJECTED as REJECTED)
from test_app_login import login, run_app
from test_services import BASE, RESULT, audit, rows

ADMIN = {"username": "admin", "role": "admin"}
KEMBLY = {"username": "kembly", "role": "lab_tech"}
CARLOS = {"username": "carlos", "role": "lab_tech"}


def sample(status=PENDING, assigned_to="kembly", result_count=1):
    return {"sample_id": "S-1", "status": status, "assigned_to": assigned_to,
            "result_count": result_count}


# ── the rules (pure) ─────────────────────────────────────────

@pytest.mark.parametrize("current, allowed_for_assignee, allowed_for_admin", [
    (PENDING, {WIP, REJECTED}, {WIP, REJECTED}),
    (WIP, {DONE, REJECTED}, {DONE, REJECTED}),
    (DONE, set(), {WIP}),               # reopening is admin-only
    (REJECTED, set(), {PENDING}),
])
def test_transition_matrix(current, allowed_for_assignee, allowed_for_admin):
    for user, allowed in ((KEMBLY, allowed_for_assignee), (ADMIN, allowed_for_admin)):
        got = {s for s in domain.SAMPLE_STATUSES if s != current
               and domain.transition_error(user, sample(current), s) is None}
        assert got == allowed, user
        assert domain.status_options(user, sample(current)) == [current, *sorted(
            allowed, key=domain.TRANSITIONS[current].index)]


def test_completing_needs_a_recorded_result():
    assert "at least one test result" in domain.transition_error(
        ADMIN, sample(WIP, result_count=0), DONE)
    assert DONE not in domain.status_options(KEMBLY, sample(WIP, result_count=0))


def test_other_techs_get_no_options():
    s = sample(PENDING, assigned_to="kembly")
    assert domain.status_options(CARLOS, s) == [PENDING]
    assert domain.assignee_options(CARLOS, s, ["kembly", "carlos"]) == ["kembly"]
    assert "Only kembly (the assignee) or an admin" in domain.change_error(CARLOS, s, WIP, "kembly")


def test_assignee_options():
    techs = ["kembly", "carlos", "maria"]
    assert domain.assignee_options(ADMIN, sample(), techs) == ["kembly", None, "carlos", "maria"]
    assert domain.assignee_options(KEMBLY, sample(), techs) == ["kembly"]
    assert domain.assignee_options(CARLOS, sample(assigned_to=None), techs) == [None, "carlos"]
    assert domain.assignee_options(ADMIN, sample(DONE), techs) == ["kembly"]   # terminal


@pytest.mark.parametrize("user, s, status, assignee, role, error", [
    (CARLOS, sample(assigned_to=None), WIP, "carlos", "lab_tech", None),      # claim + start
    (CARLOS, sample(assigned_to=None), PENDING, "maria", "lab_tech", "Only an admin can reassign"),
    (KEMBLY, sample(), PENDING, "carlos", "lab_tech", "Only an admin can reassign"),
    (KEMBLY, sample(), PENDING, None, None, "Only an admin can reassign"),    # can't drop it
    (ADMIN, sample(), PENDING, "carlos", "lab_tech", None),
    (ADMIN, sample(), PENDING, None, None, None),
    (ADMIN, sample(), PENDING, "admin", "admin", "only be assigned to lab techs"),
    (ADMIN, sample(), PENDING, "simulator", "system", "only be assigned to lab techs"),
    (ADMIN, sample(DONE), DONE, "carlos", "lab_tech", "can't be reassigned"),
    (ADMIN, sample(DONE), WIP, "carlos", "lab_tech", None),                   # reopen + reassign
])
def test_change_rules(user, s, status, assignee, role, error):
    got = domain.change_error(user, s, status, assignee, role)
    assert (got is None) if error is None else (error in got), got


@pytest.mark.parametrize("user, s, error", [
    (KEMBLY, sample(WIP), None),
    (ADMIN, sample(WIP, assigned_to="carlos"), None),
    (CARLOS, sample(WIP), "Only the assigned lab tech"),
    (KEMBLY, sample(PENDING), "only be logged while a sample is In Progress"),
    (KEMBLY, sample(DONE), "only be logged while a sample is In Progress"),
    (ADMIN, sample(REJECTED), "only be logged while a sample is In Progress"),
])
def test_result_entry_rules(user, s, error):
    got = domain.result_entry_error(user, s)
    assert (got is None) if error is None else (error in got), got


# ── enforced by the services ─────────────────────────────────

@pytest.fixture
def sid(lab_db):
    return services.register_sample(BASE, "admin")          # Pending, assigned to kembly


def update(sid, version, user, **change):
    return services.update_sample(sid, version, user, reason="because", **change)


def test_other_tech_cannot_change_sample_and_nothing_is_written(sid):
    with pytest.raises(services.PermissionDeniedError, match="Only kembly"):
        update(sid, 1, "carlos", status=WIP)
    assert rows("SELECT status, version FROM samples") == [{"status": PENDING, "version": 1}]
    assert audit("STATUS_UPDATED") == []


@pytest.mark.parametrize("who", ["system", "simulator", "nobody"])
def test_system_and_unknown_accounts_cannot_change_data(sid, who):
    with pytest.raises(services.PermissionDeniedError, match="not an account"):
        update(sid, 1, who, status=WIP)


def test_tech_can_claim_and_start_an_unassigned_sample(lab_db):
    sid = services.register_sample({**BASE, "assigned_to": None}, "admin")
    assert update(sid, 1, "carlos", status=WIP, assigned_to="carlos")
    assert {(a["action"], a["new_value"]) for a in audit() if a["user"] == "carlos"} == {
        ("STATUS_UPDATED", WIP), ("SAMPLE_ASSIGNED", "carlos")}


def test_admin_cannot_assign_to_a_non_tech(sid):
    with pytest.raises(services.PermissionDeniedError, match="lab techs"):
        update(sid, 1, "admin", assigned_to="simulator")


def test_completion_requires_a_result_then_reopen_is_admin_only(sid):
    update(sid, 1, "kembly", status=WIP)
    with pytest.raises(services.PermissionDeniedError, match="at least one test result"):
        update(sid, 2, "kembly", status=DONE)
    services.record_result({**RESULT, "sample_id": sid}, "kembly", "logged")
    assert update(sid, 2, "kembly", status=DONE)
    with pytest.raises(services.PermissionDeniedError, match="Only an admin can reopen"):
        update(sid, 3, "kembly", status=WIP)
    assert update(sid, 3, "admin", status=WIP)
    assert [a["new_value"] for a in audit("STATUS_UPDATED")] == [WIP, DONE, WIP]


def test_results_only_on_in_progress_samples_by_assignee_or_admin(sid):
    with pytest.raises(services.PermissionDeniedError, match="In Progress"):
        services.record_result({**RESULT, "sample_id": sid}, "kembly", "x")
    update(sid, 1, "kembly", status=WIP)
    with pytest.raises(services.PermissionDeniedError, match="assigned lab tech"):
        services.record_result({**RESULT, "sample_id": sid}, "carlos", "x")
    services.record_result({**RESULT, "sample_id": sid}, "admin", "x")
    assert rows("SELECT tested_by FROM test_results") == [{"tested_by": "admin"}]


# ── offered by the pages ─────────────────────────────────────

def open_page(lab_db, settings, username, page):
    settings(demo="true")
    at = login(run_app(), username, "lab2024" if username != "admin" else "admin123")
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, at.exception
    return at


def test_tracking_offers_only_allowed_statuses(sid, lab_db, settings):
    at = open_page(lab_db, settings, "kembly", "🔬  Sample Tracking")
    assert at.selectbox(key=f"status_{sid}").options == [PENDING, WIP, REJECTED]
    assert at.selectbox(key=f"assign_{sid}").options == ["kembly"]


def test_tracking_is_read_only_for_other_techs(sid, lab_db, settings):
    at = open_page(lab_db, settings, "carlos", "🔬  Sample Tracking")
    assert f"status_{sid}" not in [w.key for w in at.selectbox]
    assert any("only the assignee or an admin" in c.value for c in at.caption)


def test_result_form_lists_only_samples_open_to_the_user(sid, lab_db, settings):
    at = open_page(lab_db, settings, "kembly", "📋  Test Results")
    assert any("No samples are open for results" in i.value for i in at.info)
    update(sid, 1, "kembly", status=WIP)
    at = open_page(lab_db, settings, "kembly", "📋  Test Results")
    assert [o for o in at.selectbox[0].options if sid in o]
    at = open_page(lab_db, settings, "carlos", "📋  Test Results")
    assert any("No samples are open for results" in i.value for i in at.info)
