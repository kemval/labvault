"""
pages/test_results.py — Log and view test results, OOS flagging
"""

import streamlit as st
import pandas as pd
from datetime import date
from db import get_all_samples, get_results_for_sample, insert_test_result, log_action


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


def determine_status(value, spec_min, spec_max):
    if value is None:
        return "Fail (OOS)"
    if spec_min is not None and value < spec_min:
        return "Fail (OOS)"
    if spec_max is not None and value > spec_max:
        return "Fail (OOS)"
    return "Pass"


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
        sample_options = {f"{s['sample_id']} — {s['product_name'][:50]}": s["sample_id"]
                          for s in samples}

        with st.form("result_form", clear_on_submit=True):
            st.markdown("#### New Test Result Entry")

            selected_label = st.selectbox("Select Sample *", list(sample_options.keys()))
            sample_id      = sample_options[selected_label]

            c1, c2 = st.columns(2)
            with c1:
                test_name    = st.selectbox("Test Name *", TEST_TYPES)
                result_value = st.number_input("Result Value", value=0.0, format="%.2f")
                result_unit  = st.selectbox("Unit", UNIT_OPTIONS)
            with c2:
                spec_min  = st.number_input("Spec Minimum", value=0.0, format="%.2f")
                spec_max  = st.number_input("Spec Maximum", value=0.0, format="%.2f")
                tested_at = st.date_input("Test Date", value=date.today())

            notes = st.text_area("Notes / Observations", placeholder="e.g. Sample appeared discolored prior to testing...")

            submitted = st.form_submit_button("Submit Result", type="primary", use_container_width=True)

        if submitted:
            # Treat 0.0 min/max as "not set"
            s_min = spec_min if spec_min != 0.0 else None
            s_max = spec_max if spec_max != 0.0 else None
            status = determine_status(result_value, s_min, s_max)

            insert_test_result({
                "sample_id":    sample_id,
                "test_name":    test_name,
                "result_value": result_value,
                "result_unit":  result_unit,
                "spec_min":     s_min,
                "spec_max":     s_max,
                "status":       status,
                "tested_by":    user["username"],
                "tested_at":    tested_at.strftime("%Y-%m-%d"),
                "notes":        notes,
            })

            log_action(user["username"], "RESULT_LOGGED", "Test Results",
                       sample_id, f"{test_name}: {result_value} {result_unit} → {status}")

            if status == "Fail (OOS)":
                st.error(f"🚨 OOS RESULT: {test_name} = {result_value} {result_unit} — Outside specification. Deviation review required.")
            else:
                st.success(f"✅ Result logged: {test_name} = {result_value} {result_unit} — **{status}**")

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
            "status", "tested_by", "tested_at"
        ]]
        df.columns = [
            "Sample ID", "Product", "Test",
            "Result", "Unit", "Spec Min", "Spec Max",
            "Status", "Tested By", "Date"
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
