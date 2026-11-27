import os
import sys

import pytest
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import db  # noqa: E402


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """An empty, initialised database in a temp dir, with caches cleared."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    st.cache_data.clear()
    st.cache_resource.clear()
    db.init_db()
    yield db
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture
def settings(monkeypatch):
    """Set LabVault settings explicitly so no ambient env or secrets leak in."""
    def _set(demo="", admin_password=""):
        monkeypatch.setenv("LABVAULT_DEMO_MODE", demo)
        monkeypatch.setenv("LABVAULT_ADMIN_PASSWORD", admin_password)
    _set()
    return _set
