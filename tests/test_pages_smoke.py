"""Every page renders without an exception for an admin with data present."""
import pytest

from test_app_login import login, run_app, no_network  # noqa: F401  (fixture reuse)

PAGES = [
    "📊  Dashboard", "🧫  Sample Intake", "🔬  Sample Tracking", "📋  Test Results",
    "🔎  OOS Investigations",
    "📄  Protocols", "📏  Specifications", "📈  Reports", "🕵️  Audit Trail", "⚙️  Admin",
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


def app_pages():
    # app.py is a Streamlit script (importing it runs the app), so read its
    # PAGES table from the source.
    import ast
    import os
    tree = ast.parse(open(os.path.join(os.path.dirname(__file__), "..", "app.py")).read())
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", None) == "PAGES")
    return ast.literal_eval(node.value)


def test_smoke_list_covers_every_page():
    assert [label for label, *_ in app_pages()] == PAGES


def test_lab_tech_navigation_hides_admin_only_pages(populated):
    at = login(run_app(), "kembly", "lab2024")
    admin_only = {label for label, _, _, admin in app_pages() if admin}
    assert admin_only == {"⚙️  Admin"}
    assert not admin_only & set(at.sidebar.radio[0].options)
