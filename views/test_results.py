"""
pages/test_results.py — Log and view test results, OOS flagging
"""

import streamlit as st
import pandas as pd
from datetime import date
from db import get_all_samples, get_results_for_sample
import services
from views.ui import simulated_text, SIMULATED_LABEL


TEST_TYPES = [
    "Potency (% Label Claim)",
    "Dissolution (60 min)",
    "pH",
    "Sterility / Microbial Count",
    "Visible Particulates",
    "Water Content (%)",
    "Hardness (N)",
    "Friability (%)",
    "Disintegration Time (min)",
    "Label Review",
    "Other",
]

UNIT_OPTIONS = ["%", "pH", "CFU/mL", "CFU/g", "particles/container",
                "N", "min", "mg", "N/A", "other"]


# Tests whose result is a judgement, not a number.
QUALITATIVE_TESTS = {"Label Review"}
# Tests that may be recorded either way.
FLEXIBLE_TESTS = {"Other"}

OUTCOME_OPTIONS = ["—", "Pass", "Fail"]


def determine_status(value, spec_min, spec_max):
    if value is None:
        return "Fail (OOS)"
    if spec_min is not None and value < spec_min:
        return "Fail (OOS)"
    if spec_max is not None and value > spec_max:
        return "Fail (OOS)"
    return "Pass"


def evaluate_result(test_name, value, spec_min, spec_max, outcome):
    """
    Validate a result entry and decide its status.
    None means "not entered" for value, limits and outcome — 0 is a real
    number. Returns (status, errors); status is None when errors is non-empty.
    """
    is_qualitative = test_name in QUALITATIVE_TESTS or (
        test_name in FLEXIBLE_TESTS and value is None and outcome is not None)

    if is_qualitative:
        errors = []
        if outcome is None:
            errors.append(f"{test_name} is a pass/fail test — choose a Qualitative Outcome.")
        if value is not None or spec_min is not None or spec_max is not None:
            errors.append(f"{test_name} is a pass/fail test — leave Result Value "
                          "and the spec limits blank.")
        if errors:
            return None, errors
        return ("Pass" if outcome == "Pass" else "Fail (OOS)"), []

    errors = []
    if outcome is not None:
        errors.append("Qualitative Outcome only applies to pass/fail tests — "
                      "set it to “—” for a numeric result.")
    if value is None:
        errors.append("Result Value is required.")
    if spec_min is None and spec_max is None:
        errors.append("Enter at least one spec limit — a numeric result can't be "
                      "judged without one.")
    if spec_min is not None and spec_max is not None and spec_min > spec_max:
        errors.append("Spec Minimum can't be greater than Spec Maximum.")
    if errors:
        return None, errors
    return determine_status(value, spec_min, spec_max), []


def show():
    st.markdown("""
        <div class="lv-header">
            <div><h1>📋 Test Results</h1>
            <span>Log laboratory test results and review Out-of-Spec findings</span></div>
        </div>
    """, unsafe_allow_html=True)

    user    = st.session_state.user
    samples = get_all_samples()

    if not samples:
        st.info("No samples in the system yet. Import FDA data or register a sample first.")
        return

    tab_log, tab_view = st.tabs(["📝 Log New Result", "📊 View All Results"])

    # ── LOG NEW RESULT ────────────────────────────────────────
    with tab_log:
        sample_options = {
            f"{s['sample_id']} — {s['product_name'][:50]}"
            + (f" ({SIMULATED_LABEL})" if s.get("is_simulated") else ""): s["sample_id"]
            for s in samples}

        with st.form("result_form", clear_on_submit=True):
            st.markdown("#### New Test Result Entry")

            selected_label = st.selectbox("Select Sample *", list(sample_options.keys()))
            sample_id      = sample_options[selected_label]

            # Blank fields mean "not entered" (None) — 0 is a valid value or limit.
            c1, c2 = st.columns(2)
            with c1:
                test_name    = st.selectbox("Test Name *", TEST_TYPES)
                result_value = st.number_input("Result Value", value=None, format="%.2f",
                                               placeholder="Required for numeric tests")
                result_unit  = st.selectbox("Unit", UNIT_OPTIONS)
                outcome      = st.selectbox("Qualitative Outcome", OUTCOME_OPTIONS,
                                            help="Pass/fail tests only (e.g. Label Review). "
                                                 "Leave at “—” for numeric results.")
            with c2:
                spec_min  = st.number_input("Spec Minimum", value=None, format="%.2f",
                                            placeholder="Blank = no lower limit")
                spec_max  = st.number_input("Spec Maximum", value=None, format="%.2f",
                                            placeholder="Blank = no upper limit")
                tested_at = st.date_input("Test Date", value=date.today())

            notes = st.text_area("Notes / Observations", placeholder="e.g. Sample appeared discolored prior to testing...")

            submitted = st.form_submit_button("Submit Result", type="primary", use_container_width=True)

        if submitted:
            outcome_value = None if outcome == "—" else outcome
            status, errors = evaluate_result(test_name, result_value, spec_min, spec_max,
                                             outcome_value)
            if errors:
                for err in errors:
                    st.error(err)
                st.warning("Nothing was saved.")
                return

            if result_value is None:
                result_text, result_unit = outcome_value, "N/A"
                spec_text = "pass/fail"
            else:
                result_text = f"{result_value} {result_unit}"
                lo = "—" if spec_min is None else spec_min
                hi = "—" if spec_max is None else spec_max
                spec_text = f"spec {lo} to {hi}"

            # One transaction: the result and its RESULT_LOGGED audit row.
            try:
                services.record_result({
                    "sample_id":    sample_id,
                    "test_name":    test_name,
                    "result_value": result_value,
                    "result_unit":  result_unit,
                    "spec_min":     spec_min,
                    "spec_max":     spec_max,
                    "status":       status,
                    "tested_at":    tested_at.strftime("%Y-%m-%d"),
                    "notes":        notes,
                }, user["username"],
                    audit_detail=f"{test_name}: {result_text} ({spec_text}) → {status}")
            except services.ServiceError as e:
                st.error(str(e))
                return

            if status == "Fail (OOS)":
                st.error(f"🚨 OOS RESULT: {test_name} = {result_text} — Outside specification. Deviation review required.")
            else:
                st.success(f"✅ Result logged: {test_name} = {result_text} — **{status}**")

    # ── VIEW ALL RESULTS ──────────────────────────────────────
    with tab_view:
        st.markdown("#### All Test Results")

        filter_status = st.selectbox("Filter", ["All", "Pass", "Fail (OOS)"])

        # Gather all results across all samples
        all_results = []
        for s in samples:
            for r in get_results_for_sample(s["sample_id"]):
                r["product_name"] = s["product_name"][:50]
                all_results.append(r)

        if filter_status != "All":
            all_results = [r for r in all_results if r["status"] == filter_status]

        if not all_results:
            st.info("No results found.")
            return

        df = pd.DataFrame(all_results)[[
            "sample_id", "product_name", "test_name",
            "result_value", "result_unit", "spec_min", "spec_max",
            "status", "tested_by", "tested_at", "is_simulated"
        ]]
        df["is_simulated"] = df["is_simulated"].map(simulated_text)
        df.columns = [
            "Sample ID", "Product", "Test",
            "Result", "Unit", "Spec Min", "Spec Max",
            "Status", "Tested By", "Date", "Simulated"
        ]

        # Color OOS rows
        def color_status(val):
            if val == "Fail (OOS)":
                return "background-color: #fce4ec; color: #c62828; font-weight: 600"
            elif val == "Pass":
                return "background-color: #e8f5e9; color: #2e7d32; font-weight: 600"
            return ""

        styled = df.style.map(color_status, subset=["Status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
