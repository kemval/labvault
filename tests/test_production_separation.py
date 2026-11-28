"""Demo/production separation: no simulated data in production (roadmap 5.4, ADR 0026)."""
import os
import subprocess
import sys

import pytest

import config
import seed
import services
from repo import core
from test_app_login import APP, login, run_app  # noqa: F401
from test_simulated_flag import sample

ROOT = os.path.dirname(APP)
ADMIN_PASSWORD = "production-admin-pass-1"


def no_fetch(*_args, **_kwargs):
    raise AssertionError("openFDA must not be contacted outside demo mode")


def add_simulated_sample():
    with core.transaction() as conn:
        s = {**sample("D-0001-2024", "FDA"), "is_simulated": 1, "assigned_to": None}
        conn.execute(f"INSERT INTO samples ({', '.join(s)}) VALUES ({', '.join('?' * len(s))})",
                     list(s.values()))


# ── the simulator is demo-only ──────────────────────────────

def test_the_import_refuses_outside_demo_mode_before_fetching(lab_db, settings, monkeypatch):
    settings(admin_password=ADMIN_PASSWORD)
    monkeypatch.setattr(seed.requests, "get", no_fetch)
    with pytest.raises(services.ServiceError, match="only on demo instances"):
        services.import_fda(limit=1, user="admin")
    assert not lab_db.sample_exists()


def test_secure_instance_offers_no_import_and_no_auto_import(fresh_db, settings, monkeypatch):
    settings(admin_password=ADMIN_PASSWORD)
    calls = []
    monkeypatch.setattr(services, "import_fda", lambda **kw: calls.append(kw))
    at = run_app()
    assert "simulated lab results" not in " ".join(m.value for m in at.markdown)
    at = login(at, "admin", ADMIN_PASSWORD)
    assert calls == []                                            # empty DB, still no import
    assert not [b for b in at.button if "Import FDA" in b.label]
    assert not at.error
    # Empty-state hints point to Sample Intake, never to an import that isn't there.
    hints = " ".join(w.value for w in at.warning) + " ".join(i.value for i in at.info)
    assert "Sample Intake" in hints and "Import FDA" not in hints


def test_demo_instance_still_imports_and_says_so(fresh_db, settings, monkeypatch):
    settings(demo="true")
    calls = []
    monkeypatch.setattr(services, "import_fda",
                        lambda **kw: calls.append(kw) or {"success": False, "count": 0,
                                                          "error": "offline"})
    at = run_app()
    assert "simulated lab results" in " ".join(m.value for m in at.markdown)
    at = login(at, "admin", "admin123")
    assert calls and calls[0]["only_if_empty"] is True
    assert [b for b in at.button if "Import FDA" in b.label]


# ── demo data never becomes production data ─────────────────

def test_secure_mode_refuses_a_database_with_simulated_data(fresh_db, settings):
    add_simulated_sample()                    # no demo accounts: this check stands alone
    settings(admin_password=ADMIN_PASSWORD)
    at = run_app()
    [error] = at.error
    assert "contains simulated demo data (1 samples" in error.value
    assert "fresh database" in error.value
    assert not at.text_input                                      # no login form


def test_demo_mode_accepts_simulated_data(lab_db, settings):
    add_simulated_sample()
    settings(demo="true")
    at = run_app()
    assert not at.error and at.text_input


# ── the production build ────────────────────────────────────

def test_a_production_build_cannot_run_as_a_demo(monkeypatch):
    monkeypatch.setenv("LABVAULT_BUILD", "production")
    monkeypatch.setenv("LABVAULT_DEMO_MODE", "true")
    with pytest.raises(config.ConfigError, match="production build"):
        config.demo_mode()
    monkeypatch.setenv("LABVAULT_DEMO_MODE", "")
    assert config.demo_mode() is False


def test_the_production_build_shows_the_refusal_at_start(fresh_db, settings, monkeypatch):
    settings(demo="true")
    monkeypatch.setenv("LABVAULT_BUILD", "production")
    at = run_app()
    assert any("demo mode is not available" in e.value for e in at.error)


def test_the_image_is_a_production_build():
    with open(os.path.join(ROOT, "Dockerfile")) as f:
        assert "LABVAULT_BUILD=production" in f.read()


@pytest.mark.parametrize("env, simulated, ok, says", [
    ({"LABVAULT_BUILD": "production", "LABVAULT_DEMO_MODE": "true"}, False, False,
     "demo mode is not available"),
    ({"LABVAULT_BUILD": "production"}, True, False, "simulated demo data"),
    ({"LABVAULT_BUILD": "production"}, False, True, "Preflight ok (secure mode)"),
    ({"LABVAULT_DEMO_MODE": "true"}, True, True, "Preflight ok (demo mode)"),
])
def test_preflight(tmp_path, env, simulated, ok, says):
    db = str(tmp_path / "labvault.db")
    if simulated:
        code = (f"import sys; sys.path.insert(0, {ROOT!r}); from repo import core, schema; "
                f"core.DB_PATH = {db!r}; schema.init_db(); "
                "c = core.get_conn(); c.execute(\"INSERT INTO samples (sample_id, product_name, "
                "manufacturer, sample_type, recall_class, priority, collection_date, status, "
                "source, is_simulated) VALUES ('D-1', 'P', 'M', 'Tablet', 'Class I', 'Critical', "
                "'2026-01-01', 'Pending', 'FDA', 1)\"); c.commit()")
        subprocess.run([sys.executable, "-c", code], check=True)
    clean = {k: v for k, v in os.environ.items() if not k.startswith("LABVAULT_")}
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "preflight.py")],
                         env={**clean, "LABVAULT_DB_PATH": db, **env},
                         capture_output=True, text=True)
    assert (out.returncode == 0) is ok, out.stderr
    assert says in out.stdout + out.stderr
