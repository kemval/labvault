"""Report accuracy and OOS categories (audit M9, roadmap 3.8, ADR 0019)."""
import base64
import io
import re
import zlib

import openpyxl
import pytest

import domain
import services
from domain import (OOS_CONFIRMED, OOS_INVALIDATED, OOS_NOT_INVESTIGATED,
                    OOS_UNDER_INVESTIGATION, oos_category, spec_text)
from repo import core, results
from test_app_login import go, login, no_network, run_app  # noqa: F401
from test_result_entry import log
from test_services import BASE, rows
from views.reports import build_excel, build_pdf, report_meta, with_oos_category

OOS = "Fail (OOS)"


# ── the category rule ───────────────────────────────────────

@pytest.mark.parametrize("result, expected", [
    ({"status": "Pass"}, None),
    ({"status": OOS, "investigation_status": "Open"}, OOS_UNDER_INVESTIGATION),
    ({"status": OOS, "investigation_status": "Closed",
      "conclusion": domain.CONCLUSION_CONFIRMED}, OOS_CONFIRMED),
    ({"status": OOS, "investigation_status": "Closed",
      "conclusion": domain.CONCLUSION_LAB_ERROR}, OOS_INVALIDATED),
    ({"status": OOS, "review": "Rejected"}, OOS_INVALIDATED),
    ({"status": OOS}, OOS_NOT_INVESTIGATED),
])
def test_oos_category(result, expected):
    assert oos_category(result) == expected


@pytest.mark.parametrize("lo, hi, unit, text", [
    (80.0, 110.0, "%", "80 – 110 %"), (80.0, None, "%", "min 80 %"),
    (None, 0.0, "CFU/mL", "max 0 CFU/mL"), (None, None, "", "—"), (4.5, 7.5, "", "4.5 – 7.5"),
])
def test_spec_text_never_prints_none(lo, hi, unit, text):
    assert spec_text(lo, hi, unit) == text


@pytest.fixture
def every_kind(lab_db):
    """One OOS result in each category, plus a pass."""
    def wip():
        sid = services.register_sample(BASE, "admin")              # assigned to kembly
        services.update_sample(sid, 1, "kembly", status="In Progress", reason="start")
        return sid

    sid = wip()
    log(sid, "Potency (% Label Claim)", 100.0)                      # pass
    open_ = log(sid, "Potency (% Label Claim)", 50.0)               # under investigation
    confirmed = log(sid, "Potency (% Label Claim)", 60.0)
    lab_error = log(sid, "Potency (% Label Claim)", 70.0)
    services.close_investigation(confirmed["investigation_id"], "admin", "admin123",
                                 domain.CONCLUSION_CONFIRMED, "Retest confirmed")
    services.close_investigation(lab_error["investigation_id"], "admin", "admin123",
                                 domain.CONCLUSION_LAB_ERROR, "Pipette out of calibration")
    services.sign_result(lab_error["id"], "admin", "admin123", "Rejected", "Lab error")
    # Recorded before investigations existed: no investigation at all.
    legacy = results.insert_test_result({
        "sample_id": sid, "test_name": "pH", "result_value": 9.0, "result_unit": "pH",
        "spec_min": 4.5, "spec_max": 7.5, "status": OOS, "tested_by": "carlos",
        "tested_at": "2025-12-01", "notes": ""})
    lab_db.clear_data_caches()
    return {"open": open_["id"], "confirmed": confirmed["id"], "lab_error": lab_error["id"],
            "legacy": legacy}


def test_sql_and_python_categories_agree(every_kind):
    by_python = {r["id"]: oos_category(r) for r in results.report_results()}
    conn = core.get_conn()
    by_sql = dict(conn.execute(f"SELECT r.id, {results.OOS_CATEGORY_SQL} FROM test_results r "
                               f"{results.REVIEW_JOIN}").fetchall())
    conn.close()
    assert by_sql == by_python
    assert by_python[every_kind["legacy"]] == OOS_NOT_INVESTIGATED
    assert by_python[every_kind["lab_error"]] == OOS_INVALIDATED


def test_breakdown_counts_everything_but_headline_excludes_invalidated(every_kind):
    counts = results.oos_breakdown()
    assert {k: counts[k] for k in domain.OOS_CATEGORIES} == {
        OOS_CONFIRMED: 1, OOS_UNDER_INVESTIGATION: 1, OOS_NOT_INVESTIGATED: 1,
        OOS_INVALIDATED: 1}
    assert counts["counted"] == 3


def test_dashboard_alerts_leave_out_invalidated_results(every_kind):
    alerts = results.oos_results(10)
    assert every_kind["lab_error"] not in [a["id"] for a in alerts]
    assert {a["oos_category"] for a in alerts} == {
        OOS_CONFIRMED, OOS_UNDER_INVESTIGATION, OOS_NOT_INVESTIGATED}


def test_dashboard_shows_the_counted_total(every_kind, settings):
    settings(demo="true")
    at = login(run_app(), "kembly", "lab2024")
    [oos] = [m for m in at.metric if "OOS" in m.label]
    assert (oos.value, oos.delta) == ("3", "1 under investigation")
    assert any("1 invalidated" in e.value for e in at.error)


# ── the PDF ─────────────────────────────────────────────────

def pdf_text(pdf: bytes) -> str:
    """The text drawn on each page, from the PDF's compressed content streams."""
    chunks = []
    for stream in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        data = stream.strip()
        if data.endswith(b"~>"):                     # reportlab: ASCII85, then Flate
            data = base64.a85decode(data[:-2])
        try:
            chunks.append(zlib.decompress(data).decode("latin-1"))
        except zlib.error:
            pass
    return " ".join(re.findall(r"\((.*?)\) Tj", " ".join(chunks)))


def many(n_samples, n_oos):
    samples = [{**BASE, "sample_id": f"S-{i:04d}", "status": "Pending", "is_simulated": 0}
               for i in range(n_samples)]
    found = [{"id": i, "sample_id": f"S-{i:04d}", "test_name": "pH", "result_value": 9.0,
              "result_unit": "pH", "spec_min": None, "spec_max": 7.5, "status": OOS,
              "tested_by": "kembly", "tested_at": "2026-01-02", "notes": "",
              "investigation_status": "Open"} for i in range(n_oos)]
    return samples, found


def test_pdf_lists_every_row_with_page_numbers_and_metadata():
    samples, found = many(120, 60)
    meta = report_meta(samples, with_oos_category(found), "kembly",
                       ["Pending"], ["Major", "Minor"], schema_version=10)
    text = pdf_text(build_pdf(samples, found, meta))

    assert all(f"S-{i:04d}" in text for i in range(120))        # no 50-row cap
    assert text.count("Under investigation") >= 60               # every OOS row (no 30 cap)
    pages = re.findall(r"Page (\d+) of (\d+)", text)
    assert len(pages) > 1 and {total for _, total in pages} == {str(len(pages))}
    for expected in ("Generated by", "kembly", "Pending", "Major, Minor", "UTC"):
        assert expected in text
    assert "None" not in text and "max 7.5 pH" in text            # never "None – 7.5"


def test_pdf_escapes_markup_in_values():
    samples, found = many(1, 1)
    samples[0]["product_name"] = "<b>Bold & broken</b>"
    build_pdf(samples, found)                                    # would raise if parsed as markup


# ── Excel ───────────────────────────────────────────────────

def test_excel_states_what_it_covers(every_kind):
    found = results.report_results()
    samples = rows("SELECT * FROM samples")
    meta = report_meta(samples, with_oos_category(found), "carlos", schema_version=10)
    wb = openpyxl.load_workbook(io.BytesIO(build_excel(samples, found, meta)))
    info = {r[0]: r[1] for r in wb["Report Info"].iter_rows(min_row=2, values_only=True)}
    assert (info["Generated by"], info["Sample statuses"], info["OOS results counted"]) == \
        ("carlos", "All", 3)
    assert info[f"OOS — {OOS_INVALIDATED}"] == 1
    header = [c.value for c in wb["OOS Results"][1]]
    assert "OOS Status" in header and "Investigation Conclusion" in header
    assert wb["OOS Results"].max_row - 1 == 4                     # all four, invalidated too


# ── trend and page ──────────────────────────────────────────

def test_report_summary_counts_in_sql(every_kind):
    summary = results.report_summary()
    assert (summary["samples"], summary["results"], summary["oos_counted"]) == (1, 5, 3)
    assert summary["oos"][OOS_INVALIDATED] == 1
    # one month per tested_at; the invalidated OOS is tested but not counted
    assert sum(t for _, t, _ in summary["months"]) == 5
    assert sum(c for _, _, c in summary["months"]) == 3
    assert results.report_summary(statuses=["Completed"])["results"] == 0
    assert results.report_summary(statuses=[])["samples"] == 0      # empty filter: nothing


def test_report_rows_match_the_summary_and_carry_categories(every_kind):
    from repo.samples import report_samples
    found = results.report_results(["In Progress"], None)
    assert len(found) == results.report_summary(["In Progress"])["results"] == 5
    assert {r["oos_category"] for r in found} == {None, OOS_CONFIRMED, OOS_INVALIDATED,
                                                  OOS_UNDER_INVESTIGATION, OOS_NOT_INVESTIGATED}
    assert [s["status"] for s in report_samples(["In Progress"], ["Major"])] == ["In Progress"]
    assert report_samples(["Pending"]) == []


def test_reports_page_summarises_the_selection(every_kind, settings):
    settings(demo="true")
    at = go(login(run_app(), "kembly", "lab2024"), "Reports")
    metrics = {m.label: m.value for m in at.metric}
    assert (metrics["OOS Results (counted)"], metrics["OOS Invalidated"]) == ("3", "1")
    assert at.get("vega_lite_chart")                              # the monthly trend


# ── signatures on printed records (21 CFR 11.50, ADR 0028) ──────────────────

def signed_at(result_id):
    [r] = rows(f"SELECT signed_at FROM result_signatures WHERE result_id = {result_id}")
    return r["signed_at"].replace("T", " ").removesuffix("Z") + " UTC"


def test_excel_shows_who_signed_when_and_what_it_means(every_kind):
    services.sign_result(every_kind["confirmed"], "admin", "admin123", "Approved")
    found = results.report_results()
    wb = openpyxl.load_workbook(io.BytesIO(build_excel(rows("SELECT * FROM samples"), found)))
    for sheet in ("Test Results", "OOS Results"):
        ws = wb[sheet]
        header = [c.value for c in ws[1]]
        assert {"Signature", "Signed By", "Signed At (UTC)", "Signature Reason"} <= set(header)
        signed = {r[header.index("Signature")]: r for r in ws.iter_rows(min_row=2, values_only=True)
                  if r[header.index("Signature")]}
        approved, rejected = signed["Approved"], signed["Rejected"]
        assert approved[header.index("Signed By")] == "admin"
        assert approved[header.index("Signed At (UTC)")]
        assert rejected[header.index("Signature Reason")] == "Lab error"


def test_pdf_shows_who_signed_when_and_what_it_means(every_kind):
    services.sign_result(every_kind["confirmed"], "admin", "admin123", "Approved")
    text = pdf_text(build_pdf(rows("SELECT * FROM samples"), results.report_results()))
    assert f"Approved by admin, {signed_at(every_kind['confirmed'])}" in text
    assert f"Rejected by admin, {signed_at(every_kind['lab_error'])}: Lab error" in text
    assert "Not signed" in text                                   # the open and legacy OOS


def test_results_page_shows_when_a_result_was_signed(every_kind, settings):
    settings(demo="true")
    at = go(login(run_app(), "admin", "admin123"), "Test Results")
    shown = " ".join(str(df.value.to_dict()) for df in at.dataframe)
    assert f"Rejected by admin, {signed_at(every_kind['lab_error'])}: Lab error" in shown
