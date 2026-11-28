"""Every page renders without an exception for an admin with data present."""
import pytest

from test_app_login import go, login, registered_pages, run_app, no_network  # noqa: F401  (fixture reuse)

from views.navigation import PAGES, pages_for

TITLES = [title for title, *_ in PAGES]


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


@pytest.mark.parametrize("page", TITLES)
def test_page_renders(populated, page):
    at = login(run_app(), "admin", "admin123")
    go(at, page)
    assert not at.exception, at.exception


def test_every_page_file_exists_and_runs_as_a_page():
    import os
    root = os.path.join(os.path.dirname(__file__), "..")
    for _, path, icon, _ in PAGES:
        source = open(os.path.join(root, path)).read()
        assert 'if __name__ == "__main__":' in source, path
        assert icon.startswith(":material/"), path       # aria-hidden icons, not emoji


def test_lab_tech_navigation_hides_admin_only_pages(populated):
    at = login(run_app(), "kembly", "lab2024")
    assert [t for t, *_, admin in PAGES if admin] == ["Admin"]
    assert "Admin" not in registered_pages(at)
    assert [t for t, *_ in pages_for("lab_tech")] == [t for t in TITLES if t != "Admin"]
    with pytest.raises(ValueError, match="not a registered page|Could not find"):
        at.switch_page("views/admin.py")


def test_admin_sees_every_page(populated):
    at = login(run_app(), "admin", "admin123")
    assert registered_pages(at) == TITLES
