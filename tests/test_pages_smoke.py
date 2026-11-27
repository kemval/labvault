"""Every page renders without an exception for an admin with data present."""
import pytest

from test_app_login import login, run_app, no_network  # noqa: F401  (fixture reuse)

PAGES = [
    "📊  Dashboard", "🧫  Sample Intake", "🔬  Sample Tracking", "📋  Test Results",
    "📄  Protocols", "📈  Reports", "🕵️  Audit Trail", "⚙️  Admin",
]


@pytest.fixture
def populated(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    fresh_db.seed_protocols()
    fresh_db.insert_sample({
        "sample_id": "S-1", "product_name": "Metformin 500mg", "lot_number": "AB1234",
        "manufacturer": "Acme", "sample_type": "Tablet", "recall_class": "Class II",
        "priority": "Major", "reason_for_recall": "Dissolution failure",
        "collection_date": "2026-01-01", "status": "Pending", "assigned_to": "kembly",
        "protocol_id": None, "notes": "", "source": "Manual",
    })
    fresh_db.insert_test_result({
        "sample_id": "S-1", "test_name": "Dissolution (60 min)", "result_value": 70.0,
        "result_unit": "%", "spec_min": 80.0, "spec_max": None, "status": "Fail (OOS)",
        "tested_by": "kembly", "tested_at": "2026-01-02", "notes": "",
    })
    return fresh_db


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(populated, page):
    at = login(run_app(), "admin", "admin123")
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, at.exception
