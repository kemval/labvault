"""Drives the real app.py through Streamlit's headless AppTest runner."""
import os

import pytest
from streamlit.testing.v1 import AppTest

import services

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    # The first-login FDA auto-import must not hit the network in tests.
    monkeypatch.setattr(services, "import_fda",
                        lambda limit=100, only_if_empty=False, user="system":
                        {"success": False, "error": "offline", "count": 0})


def run_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def go(at, title):
    """Open a page by its navigation title, as a click in the sidebar would."""
    from views.navigation import PAGES
    path = next(path for t, path, *_ in PAGES if t == title)
    at.switch_page(path).run()
    assert not at.exception, at.exception
    return at


def registered_pages(at):
    """Titles of the pages st.navigation registered for this session."""
    return [info["page_name"] for info in at._registered_pages.values()]


def page_text(at):
    return " ".join(str(e.value) for e in list(at.markdown) + list(at.caption) + list(at.code))


def login(at, username, password):
    at.text_input[0].input(username)
    at.text_input[1].input(password)
    at.button[0].click().run()
    assert not at.exception, at.exception
    return at


def test_demo_login_page_shows_demo_credentials(fresh_db, settings):
    settings(demo="true")
    at = run_app()
    assert "admin123" in page_text(at)


def test_demo_user_can_still_log_in(fresh_db, settings):
    settings(demo="true")
    at = login(run_app(), "admin", "admin123")
    assert at.session_state.logged_in is True
    assert at.session_state.user["role"] == "admin"


def test_secure_mode_hides_credentials_and_rejects_demo_password(fresh_db, settings):
    settings(admin_password="a-long-secret-pw")
    at = run_app()
    assert "admin123" not in page_text(at)
    assert "lab2024" not in page_text(at)

    login(at, "admin", "admin123")
    assert at.session_state.logged_in is False
    assert any("Invalid username or password" in e.value for e in at.error)


def test_secure_mode_admin_logs_in_and_admin_page_hides_demo_block(fresh_db, settings):
    settings(admin_password="a-long-secret-pw")
    at = login(run_app(), "admin", "a-long-secret-pw")
    assert at.session_state.logged_in is True

    go(at, "Admin")
    assert not at.exception, at.exception
    assert any("Admin Panel" in m.value for m in at.markdown)
    assert "admin123" not in page_text(at)


def test_unconfigured_deployment_does_not_start(fresh_db, settings):
    at = run_app()
    assert any("not configured correctly" in e.value for e in at.error)
    assert len(at.text_input) == 0  # no login form rendered
