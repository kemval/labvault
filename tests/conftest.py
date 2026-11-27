import os
import sys

import pytest
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import db  # noqa: E402
from repo import audit, core, fda_import, protocols, results, samples, schema, users  # noqa: E402

_REPO_MODULES = (core, schema, users, audit, samples, results, protocols, fda_import)


class TestDB:
    """
    One handle for tests: cached reads from db.py first, then repo/ functions.
    Repo writes don't clear the Streamlit caches (services.py does that in the
    app), so calls made through this handle clear them afterwards — fixture
    data is then visible to the cached reads the views use.
    """

    __test__ = False  # not a test class

    @property
    def DB_PATH(self):
        return core.DB_PATH

    def __getattr__(self, name):
        if hasattr(db, name):
            return getattr(db, name)
        for module in _REPO_MODULES:
            if hasattr(module, name):
                target = getattr(module, name)
                if not callable(target):
                    return target

                def call(*args, **kwargs):
                    try:
                        return target(*args, **kwargs)
                    finally:
                        st.cache_data.clear()
                return call
        raise AttributeError(name)


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """An empty, initialised database in a temp dir, with caches cleared."""
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "test.db"))
    st.cache_data.clear()
    st.cache_resource.clear()
    schema.init_db()
    yield TestDB()
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
