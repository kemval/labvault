import os
import sys

import pytest
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import db  # noqa: E402
import services  # noqa: E402
from repo import (audit, core, fda_import, passwords, protocols, results, samples, schema,  # noqa: E402
                  specifications, users)

_REPO_MODULES = (core, schema, users, audit, samples, results, protocols, fda_import,
                 specifications)


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
def lab_db(fresh_db):
    """fresh_db with the demo accounts, for tests that write as kembly etc.
    (samples, results and audit rows must reference real users)."""
    fresh_db.seed_users(demo=True)
    specifications.seed_specifications()       # demo limits, so results can be logged
    return fresh_db


def insert_legacy_result(data: dict):
    """A result row in the baseline columns — for tests that build an
    older schema (before migration 5) and then migrate it."""
    cols = ("sample_id", "test_name", "result_value", "result_unit", "spec_min",
            "spec_max", "status", "tested_by", "tested_at", "notes")
    with core.transaction() as conn:
        conn.execute(f"INSERT INTO test_results ({', '.join(cols)}) "
                     f"VALUES ({', '.join('?' * len(cols))})", [data[c] for c in cols])


@pytest.fixture
def settings(monkeypatch):
    """Set LabVault settings explicitly so no ambient env or secrets leak in."""
    def _set(demo="", admin_password=""):
        monkeypatch.setenv("LABVAULT_DEMO_MODE", demo)
        monkeypatch.setenv("LABVAULT_ADMIN_PASSWORD", admin_password)
    _set()
    return _set


@pytest.fixture(autouse=True)
def never_the_real_database(tmp_path, monkeypatch):
    """core.DB_PATH defaults to ./labvault.db — the developer's real data.
    Every test starts pointed at a throwaway path instead; fresh_db and
    friends then override it with their own."""
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "no-database-configured.db"))
    # Nor the developer's real alert channel (ADR 0025).
    monkeypatch.delenv("LABVAULT_ALERT_URL", raising=False)


@pytest.fixture(autouse=True)
def cheap_password_hashing(monkeypatch):
    """Real scrypt costs ~140 ms per hash; tests use a tiny cost. The cost is
    stored with each hash, so verification is unaffected."""
    monkeypatch.setattr(passwords, "COST", {"n": 2 ** 4, "r": 1, "p": 1})


@pytest.fixture
def open_sample(lab_db):
    """An In Progress Injectable assigned to kembly, with the demo specs."""
    specifications.seed_specifications()
    sid = services.register_sample({
        "product_name": "Ceftriaxone Injection", "lot_number": "", "manufacturer": "M",
        "sample_type": "Injectable", "recall_class": "Class I", "priority": "Critical",
        "reason_for_recall": "", "collection_date": "2026-01-01", "assigned_to": "kembly",
        "protocol_id": None, "notes": ""}, "admin")
    services.update_sample(sid, 1, "kembly", status="In Progress", reason="start")
    return sid


@pytest.fixture(autouse=True)
def logged_errors(request):
    """
    The app turns unexpected exceptions into a message plus a logged error
    (ADR 0021), so AppTest's `at.exception` no longer sees them. Any error
    LabVault logs therefore fails the test, unless the test is marked
    @pytest.mark.logs_errors and inspects the list this fixture returns.
    """
    import logging
    from logs import LOGGER

    class Collect(logging.Handler):
        def emit(self, record):
            seen.append(record)

    seen = []
    handler = Collect(level=logging.ERROR)
    logger = logging.getLogger(LOGGER)
    logger.addHandler(handler)
    yield seen
    logger.removeHandler(handler)
    if not request.node.get_closest_marker("logs_errors"):
        assert not seen, "LabVault logged an error:\n" + "\n".join(
            f"{r.getMessage()} ({r.exc_info[1]!r})" if r.exc_info else r.getMessage()
            for r in seen)
