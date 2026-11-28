"""Specification master data (audit H4d, migration 5, ADR 0012)."""
import pytest

import seed
import services
from repo import specifications
from test_app_login import go, login, run_app
from test_services import audit

POTENCY = "Potency (% Label Claim)"


def save(lo, hi, user="admin", reason="", version=None, sample_type="Tablet",
         test="Hardness (N)", unit="N"):
    return services.save_specification(sample_type, test, lo, hi, unit, user,
                                       reason=reason, expected_version=version)


# ── maintenance ──────────────────────────────────────────────

def test_admin_creates_then_changes_with_reason_old_and_new_values(lab_db):
    assert save(40.0, None)["version"] == 1
    assert save(50.0, 120.0, reason="New tooling", version=1)["version"] == 2
    created, updated = audit("SPEC_CREATED")[-1], audit("SPEC_UPDATED")[0]
    assert (created["target_id"], created["new_value"]) == ("Tablet × Hardness (N)", "40 to — N")
    assert (updated["old_value"], updated["new_value"], updated["reason"]) == \
        ("40 to — N", "50 to 120 N", "New tooling")


def test_change_needs_a_reason(lab_db):
    save(40.0, None)
    with pytest.raises(services.ServiceError, match="reason"):
        save(50.0, None, version=1)
    assert specifications.find_spec("Tablet", "Hardness (N)")["spec_min"] == 40.0


def test_stale_change_is_rejected(lab_db):
    save(40.0, None)
    save(45.0, None, reason="first", version=1)
    with pytest.raises(services.ConcurrentUpdateError, match="now v2"):
        save(50.0, None, reason="second", version=1)


def test_saving_unchanged_limits_writes_nothing(lab_db):
    save(40.0, None)
    assert save(40.0, None, version=1)["version"] == 1
    assert audit("SPEC_UPDATED") == []


@pytest.mark.parametrize("kwargs, error", [
    ({"lo": None, "hi": None}, "at least one limit"),
    ({"lo": 10.0, "hi": 5.0}, "can't be greater"),
    ({"lo": 1.0, "hi": None, "test": "Label Review"}, "not a numeric test"),
    ({"lo": 1.0, "hi": None, "sample_type": "Non-sterile"}, "Unknown sample type"),
    ({"lo": 1.0, "hi": None, "unit": "furlongs"}, "Unknown unit"),
])
def test_invalid_specifications_are_refused(lab_db, kwargs, error):
    with pytest.raises(services.ServiceError, match=error):
        save(**kwargs)


@pytest.mark.parametrize("who", ["kembly", "system"])
def test_only_admins_maintain_specifications(lab_db, who):
    with pytest.raises(services.PermissionDeniedError):
        save(40.0, None, user=who)
    assert specifications.find_spec("Tablet", "Hardness (N)") is None


# ── defaults ─────────────────────────────────────────────────

def test_default_specs_match_the_limits_the_simulator_uses():
    # Demo specs must agree with the simulated results they sit next to.
    simulated = {}
    for reason in ["failed dissolution", "superpotent", "subpotent", "sterility",
                   "particulate matter", "ph out of range", "mislabeled", "other"]:
        for _ in range(20):
            for r in seed.simulate_test_results("S", reason, "Tablet", "simulator", "2024-01-01"):
                if r["spec_min"] is not None or r["spec_max"] is not None:
                    simulated[r["test_name"]] = (r["spec_min"], r["spec_max"], r["result_unit"])
    for _types, test, lo, hi, unit in specifications.DEFAULT_SPECS:
        assert simulated[test] == (lo, hi, unit), test


def test_demo_instance_seeds_default_specs(fresh_db, settings):
    settings(demo="true")
    login(run_app(), "admin", "admin123")
    assert specifications.find_spec("Tablet", POTENCY)["spec_max"] == 110.0


def test_secure_instance_starts_without_specs(fresh_db, settings):
    settings(admin_password="a-long-admin-password")
    run_app()
    assert specifications.all_specs() == []


# ── the page ─────────────────────────────────────────────────

def open_specs(username, password):
    at = login(run_app(), username, password)
    go(at, "Specifications")
    assert not at.exception, at.exception
    return at


def test_admin_changes_a_spec_on_the_page(lab_db, settings):
    settings(demo="true")
    at = open_specs("admin", "admin123")
    at.selectbox(key="spec_test").set_value(POTENCY).run()
    assert any("Current: v1 — 90 to 110 %" in c.value for c in at.caption)
    next(w for w in at.number_input if w.label == "Minimum").set_value(95.0)
    next(w for w in at.text_input if w.label.startswith("Reason")).input("Tighter release spec")
    next(b for b in at.button if b.label == "Save specification").click().run()
    assert not at.exception, at.exception
    spec = specifications.find_spec("Tablet", POTENCY)
    assert (spec["spec_min"], spec["version"]) == (95.0, 2)
    assert any("as v2" in s.value for s in at.success)


def test_lab_tech_sees_specs_read_only(lab_db, settings):
    settings(demo="true")
    at = open_specs("kembly", "lab2024")
    assert len(at.dataframe[0].value) == len(specifications.all_specs())
    assert not [b for b in at.button if b.label == "Save specification"]
    assert any("Only an admin" in c.value for c in at.caption)
