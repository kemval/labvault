"""First-login auto-import behaviour in the real app (audit C6)."""
import pytest

import services
from test_app_login import login, run_app


@pytest.fixture
def import_calls(monkeypatch):
    calls = []

    def fake(limit=100, only_if_empty=False, user="system"):
        calls.append((only_if_empty, user))
        return {"success": False, "error": "API down", "count": 0}

    monkeypatch.setattr(services, "import_fda", fake)
    return calls


def test_failed_auto_import_is_attempted_once_and_reported(fresh_db, settings, import_calls):
    settings(demo="true")
    at = login(run_app(), "kembly", "lab2024")

    assert import_calls == [(True, "kembly")]  # once, only-if-empty, credited to the user
    assert any("Could not import FDA data: API down" in e.value for e in at.error)
    assert any("Ask an administrator" in e.value for e in at.error)

    # Further interactions must not re-trigger the import.
    for page in ["🔬  Sample Tracking", "📊  Dashboard"]:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, at.exception
    assert import_calls == [(True, "kembly")]


def test_admin_gets_retry_hint(fresh_db, settings, import_calls):
    settings(demo="true")
    at = login(run_app(), "admin", "admin123")
    assert any("Import FDA Data" in e.value for e in at.error)


def test_no_auto_import_when_samples_exist(fresh_db, settings, import_calls):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    fresh_db.insert_sample({
        "sample_id": "S-1", "product_name": "P", "lot_number": "", "manufacturer": "M",
        "sample_type": "Tablet", "recall_class": "Class II", "priority": "Major",
        "reason_for_recall": "", "collection_date": "2026-01-01", "status": "Pending",
        "assigned_to": "kembly", "protocol_id": None, "notes": "", "source": "Manual",
    })
    login(run_app(), "admin", "admin123")
    assert import_calls == []


def test_admin_import_button_credits_the_admin(fresh_db, settings, import_calls):
    settings(demo="true")
    at = login(run_app(), "admin", "admin123")        # auto-import fails (fake API down)
    next(b for b in at.sidebar.button if "Import FDA Data" in b.label).click().run()
    assert import_calls == [(True, "admin"), (False, "admin")]
