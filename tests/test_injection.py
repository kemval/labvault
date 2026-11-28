"""Stored data is never interpreted as HTML or as spreadsheet formulas (audit H2, H3)."""
import io

import openpyxl

import services

from test_app_login import login, run_app, no_network  # noqa: F401

PAYLOAD = '<img src=x onerror="alert(1)">'


def add_hostile_sample(db):
    db.insert_sample({
        "sample_id": "S-X", "product_name": PAYLOAD, "lot_number": "<b>lot</b>",
        "manufacturer": "<script>x()</script>", "sample_type": "Tablet",
        "recall_class": "Class II", "priority": "Major", "reason_for_recall": PAYLOAD,
        "collection_date": "2026-01-01", "status": "Pending", "assigned_to": "kembly",
        "protocol_id": None, "notes": "", "source": "Manual",
    })


def html_bodies(at):
    return [m.value for m in at.markdown if m.allow_html]


def assert_escaped(at):
    bodies = " ".join(html_bodies(at))
    assert "&lt;img src=x" in bodies           # the value is rendered...
    assert "<img" not in bodies                 # ...but never as markup
    assert "<script" not in bodies and "<b>lot" not in bodies


def test_dashboard_escapes_stored_values(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    add_hostile_sample(fresh_db)
    services.log_event("kembly", "SAMPLE_CREATED", "Sample Intake", "S-X", PAYLOAD)

    at = login(run_app(), "admin", "admin123")
    assert_escaped(at)


def test_sample_tracking_escapes_stored_values(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    add_hostile_sample(fresh_db)

    at = login(run_app(), "admin", "admin123")
    at.sidebar.radio[0].set_value("🔬  Sample Tracking").run()
    at.selectbox(key="trk_open").set_value("S-X").run()     # the detail panel is HTML
    assert not at.exception, at.exception
    assert_escaped(at)


def test_excel_export_never_contains_formulas():
    from views.reports import build_excel
    formula = '=HYPERLINK("http://evil.example","Click")'
    samples = [{
        "sample_id": "S-1", "product_name": formula, "manufacturer": "=1+1",
        "lot_number": "@SUM(A1)", "sample_type": "Tablet", "recall_class": "Class II",
        "priority": "Major", "status": "Pending", "assigned_to": "kembly",
        "collection_date": "2026-01-01", "reason_for_recall": "-2+3",
    }]
    results = [{
        "sample_id": "S-1", "test_name": "pH", "result_value": -1.5, "result_unit": "pH",
        "spec_min": 4.5, "spec_max": 7.5, "status": "Fail (OOS)", "tested_by": "kembly",
        "tested_at": "2026-01-02", "notes": formula,
    }]

    wb = openpyxl.load_workbook(io.BytesIO(build_excel(samples, results)))

    cells = [c for ws in wb.worksheets for row in ws.iter_rows() for c in row]
    assert not [c.coordinate for c in cells if c.data_type == "f"]
    values = {c.value for c in cells}
    assert {formula, "=1+1", "@SUM(A1)", "-2+3"} <= values   # text preserved exactly
    assert -1.5 in values                                     # numbers stay numeric
    assert wb.sheetnames == ["Samples", "Test Results", "OOS Results"]
