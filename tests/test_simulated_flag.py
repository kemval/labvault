"""Simulated demo data is flagged and visibly marked everywhere (audit C4)."""
import io

import openpyxl
import pytest

import domain
import services
from fake_fda import record, serve
from test_app_login import login, run_app  # samples always exist here, so no auto-import


def sample(sample_id, source, **extra):
    base = {
        "sample_id": sample_id, "product_name": f"Product {sample_id}", "lot_number": "",
        "manufacturer": "M", "sample_type": "Tablet", "recall_class": "Class II",
        "priority": "Major", "reason_for_recall": "", "collection_date": "2024-01-01",
        "status": "Pending", "assigned_to": "kembly", "protocol_id": None,
        "notes": "", "source": source,
    }
    base.update(extra)
    return base


def result(sample_id, notes, value=95.0):
    return {
        "sample_id": sample_id, "test_name": "Potency (% Label Claim)", "result_value": value,
        "result_unit": "%", "spec_min": 90.0, "spec_max": 110.0, "status": "Pass",
        "tested_by": "kembly", "tested_at": "2024-01-02", "notes": notes,
    }


def rows(db, sql):
    conn = db.get_conn()
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


# ── migration 1 on a pre-existing database ─────────────────────────────────

def test_migration_flags_existing_demo_data_only(tmp_path, monkeypatch):
    from repo import core, schema, users
    from conftest import insert_legacy_result as insert_test_result
    from repo.samples import insert_sample
    monkeypatch.setattr(core, "DB_PATH", str(tmp_path / "old.db"))
    with monkeypatch.context() as m:
        m.setattr(schema, "MIGRATIONS", [])
        schema.init_db()                           # baseline schema, version 0
        users.seed_users(demo=True)                # samples/results name kembly
        insert_sample(sample("D-1", "FDA"))
        insert_test_result(result("D-1", "Within specification."))            # simulator
        insert_test_result(result("D-1", "Retest by analyst B, new column"))  # hand-logged
        insert_sample(sample("M-1", "Manual"))
        insert_test_result(result("M-1", "Within specification."))            # real sample

    schema.apply_migrations()

    flags = {r["sample_id"]: r["is_simulated"] for r in rows(core, "SELECT * FROM samples")}
    assert flags == {"D-1": 1, "M-1": 0}
    res = {r["notes"] + "|" + r["sample_id"]: r["is_simulated"]
           for r in rows(core, "SELECT * FROM test_results")}
    assert res == {"Within specification.|D-1": 1,
                   "Retest by analyst B, new column|D-1": 0,
                   "Within specification.|M-1": 0}
    [audit] = rows(core, "SELECT * FROM audit_trail WHERE action = 'SCHEMA_MIGRATED'")
    assert "1 FDA-imported samples and 1 simulator-generated" in audit["detail"]
    assert schema.schema_version(core.get_conn()) == len(schema.MIGRATIONS)


def test_migration_on_empty_database_writes_no_audit(fresh_db):
    assert rows(fresh_db, "SELECT * FROM audit_trail") == []


# ── new data ────────────────────────────────────────────────────────────────

def test_new_imports_are_flagged_and_attributed_to_simulator(fresh_db, monkeypatch):
    serve(monkeypatch, [record(1), record(2, reason="Superpotent drug")])
    services.import_fda(limit=2)

    assert {r["is_simulated"] for r in rows(fresh_db, "SELECT * FROM samples")} == {1}
    results = rows(fresh_db, "SELECT * FROM test_results")
    assert results and {r["is_simulated"] for r in results} == {1}
    assert {r["tested_by"] for r in results} == {domain.SIMULATOR_USER}
    assert all("SIMULATED" in r["notes"] for r in rows(fresh_db, "SELECT * FROM samples"))


def test_manually_registered_data_is_real(lab_db):
    lab_db.insert_sample(sample("M-1", "Manual"))
    lab_db.insert_test_result(result("M-1", "ok"))
    assert rows(lab_db, "SELECT is_simulated FROM samples") == [{"is_simulated": 0}]
    assert rows(lab_db, "SELECT is_simulated FROM test_results") == [{"is_simulated": 0}]
    assert lab_db.count_simulated() == {"samples": 0, "results": 0}


# ── UI ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def mixed_app(fresh_db, settings, monkeypatch):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    serve(monkeypatch, [record(1)])
    services.import_fda(limit=1)                       # D-0001-2024, simulated
    fresh_db.insert_sample(sample("M-1", "Manual"))   # real
    return login(run_app(), "admin", "admin123")


def test_notice_shows_simulated_counts(mixed_app):
    assert any("Demo data:" in i.value and "1 samples and 2 test results" in i.value
               for i in mixed_app.info)


def test_no_notice_without_simulated_data(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    fresh_db.insert_sample(sample("M-1", "Manual"))
    at = login(run_app(), "admin", "admin123")
    assert not any("Demo data:" in i.value for i in at.info)


def test_dashboard_badges_only_simulated_samples(mixed_app):
    cards = [m.value for m in mixed_app.markdown if m.allow_html and "badge-sim" in m.value
             and "SIMULATED" in m.value and "<style>" not in m.value]
    assert len(cards) == 1 and "D-0001-2024" in cards[0]


def test_tracking_labels_simulated_samples(mixed_app):
    mixed_app.sidebar.radio[0].set_value("🔬  Sample Tracking").run()
    assert not mixed_app.exception, mixed_app.exception
    labels = {e.label for e in mixed_app.expander}
    assert any("D-0001-2024" in label and "SIMULATED" in label for label in labels)
    assert any("M-1" in label and "SIMULATED" not in label for label in labels)


# ── reports ─────────────────────────────────────────────────────────────────

def test_excel_marks_simulated_rows(lab_db, monkeypatch):
    from views.reports import build_excel
    serve(monkeypatch, [record(1)])
    services.import_fda(limit=1)
    lab_db.insert_sample(sample("M-1", "Manual"))
    lab_db.insert_test_result(result("M-1", "ok"))

    wb = openpyxl.load_workbook(io.BytesIO(build_excel(
        lab_db.get_all_samples(), lab_db.get_all_results())))

    for name in ("Samples", "Test Results"):
        ws = wb[name]
        header = [c.value for c in ws[1]]
        sim = header.index("Simulated")
        by_id = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            by_id.setdefault(row[0], set()).add(row[sim])
        assert by_id["D-0001-2024"] == {"Yes"} and by_id["M-1"] == {"No"}, name


def test_pdf_states_simulated_counts(lab_db, monkeypatch):
    from reportlab import rl_config
    from views.reports import build_pdf
    monkeypatch.setattr(rl_config, "pageCompression", 0)
    serve(monkeypatch, [record(1)])
    services.import_fda(limit=1)

    pdf = build_pdf(lab_db.get_all_samples(), lab_db.get_all_results())

    assert b"Contains simulated demo data" in pdf
    assert b"D-0001-2024 *" in pdf
