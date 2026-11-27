"""Sample Tracking and Intake through the real UI (audit H8)."""
import pytest

import db
import services
from test_app_login import login, run_app
from test_services import BASE, audit, rows


@pytest.fixture
def tracking(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    sample_id = services.register_sample(BASE, "admin")
    at = login(run_app(), "kembly", "lab2024")
    at.sidebar.radio[0].set_value("🔬  Sample Tracking").run()
    assert not at.exception, at.exception
    return at, sample_id


def save(at, sample_id, status):
    at.selectbox(key=f"status_{sample_id}").set_value(status)
    at.button(key=f"save_{sample_id}").click().run()
    assert not at.exception, at.exception
    return at


def test_save_updates_sample_and_audit(tracking):
    at, sample_id = tracking
    save(at, sample_id, "In Progress")
    [s] = rows("SELECT * FROM samples")
    assert (s["status"], s["version"]) == ("In Progress", 2)
    assert audit("STATUS_UPDATED")[0]["user"] == "kembly"


def test_concurrent_edit_is_rejected_and_other_users_change_kept(tracking):
    at, sample_id = tracking
    # Someone else saves after this page was rendered (e.g. in another process).
    services.update_sample(sample_id, 1, "carlos", status="Rejected")
    db.get_all_samples.clear()

    at = save(at, sample_id, "Completed")

    assert any("changed by someone else" in e.value for e in at.error)
    assert any("Someone else changed this sample" in w.value for w in at.warning)
    assert rows("SELECT status, version FROM samples") == [{"status": "Rejected", "version": 2}]
    assert [a["user"] for a in audit("STATUS_UPDATED")] == ["carlos"]


def test_reload_adopts_current_values_then_saves(tracking):
    at, sample_id = tracking
    services.update_sample(sample_id, 1, "carlos", status="Rejected")
    db.get_all_samples.clear()
    at.run()

    at.button(key=f"reload_btn_{sample_id}").click().run()
    assert at.selectbox(key=f"status_{sample_id}").value == "Rejected"
    assert not any("Someone else changed" in w.value for w in at.warning)

    save(at, sample_id, "In Progress")
    assert rows("SELECT status, version FROM samples") == [{"status": "In Progress", "version": 3}]


def test_consecutive_saves_by_same_user_both_succeed(tracking):
    at, sample_id = tracking
    save(at, sample_id, "In Progress")
    save(at, sample_id, "Completed")
    assert rows("SELECT status, version FROM samples") == [{"status": "Completed", "version": 3}]
    assert not at.error


def test_intake_form_registers_sample_with_audit(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    fresh_db.insert_sample({**BASE, "sample_id": "S-0", "status": "Pending", "source": "Manual"})
    at = login(run_app(), "kembly", "lab2024")
    at.sidebar.radio[0].set_value("🧫  Sample Intake").run()
    [product, manufacturer] = [w for w in at.text_input if w.label.endswith("*")]
    product.input("Amoxicillin 250mg")
    manufacturer.input("Acme")
    next(b for b in at.button if b.label == "Register Sample").click().run()
    assert not at.exception, at.exception

    [new] = rows("SELECT * FROM samples WHERE sample_id != 'S-0'")
    assert new["product_name"] == "Amoxicillin 250mg"
    assert audit("SAMPLE_CREATED")[0]["target_id"] == new["sample_id"]
    assert any(new["sample_id"] in s.value for s in at.success)


def test_status_save_keeps_unassigned_sample_unassigned(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    sample_id = services.register_sample({**BASE, "assigned_to": None}, "admin")
    at = login(run_app(), "kembly", "lab2024")
    at.sidebar.radio[0].set_value("🔬  Sample Tracking").run()
    assert at.selectbox(key=f"assign_{sample_id}").value == "Unassigned"

    save(at, sample_id, "In Progress")

    [s] = rows("SELECT * FROM samples")
    assert (s["status"], s["assigned_to"]) == ("In Progress", None)
    assert audit("SAMPLE_ASSIGNED") == []
