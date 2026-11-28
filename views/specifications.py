"""
views/specifications.py — acceptance limits per sample type × test (ADR 0012).
Everyone can read them; only admins create or change them. Results are
judged against these limits — analysts no longer type their own.
"""

import pandas as pd
import streamlit as st

import services
from db import get_all_specifications
from domain import QUANTITATIVE_TESTS, SAMPLE_TYPES, UNITS, is_admin
from views.ui import page_header


def _fmt(value):
    return "—" if value is None or pd.isna(value) else f"{value:g}"


def show():
    page_header("📏 Specifications", "Acceptance limits per sample type and test")
    user = st.session_state.user
    specs = get_all_specifications()
    if "spec_saved" in st.session_state:
        st.success(st.session_state.pop("spec_saved"))

    if specs:
        df = pd.DataFrame(specs)[["sample_type", "test_name", "spec_min", "spec_max",
                                  "unit", "version", "updated_by", "updated_at"]]
        df["spec_min"] = df["spec_min"].map(_fmt)
        df["spec_max"] = df["spec_max"].map(_fmt)
        df.columns = ["Sample Type", "Test", "Min", "Max", "Unit", "Version",
                      "Updated By", "Updated At (UTC)"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No specifications defined yet. Numeric results can't be logged until "
                "an admin adds the specification for that sample type and test.")

    if not is_admin(user):
        st.caption("Only an admin can create or change specifications.")
        return

    st.markdown("---")
    st.markdown("#### Create or change a specification")
    # Chosen outside the form so the current values below follow the selection.
    c1, c2 = st.columns(2)
    sample_type = c1.selectbox("Sample Type", SAMPLE_TYPES, key="spec_type")
    test_name = c2.selectbox("Test", QUANTITATIVE_TESTS, key="spec_test")
    current = next((s for s in specs if s["sample_type"] == sample_type
                    and s["test_name"] == test_name), None)
    if current:
        st.caption(f"Current: v{current['version']} — {_fmt(current['spec_min'])} to "
                   f"{_fmt(current['spec_max'])} {current['unit']}. Results already recorded "
                   "keep the limits they were judged against.")
    else:
        st.caption("No specification yet for this sample type and test.")

    with st.form(f"spec_form_{sample_type}_{test_name}"):
        f1, f2, f3 = st.columns(3)
        spec_min = f1.number_input("Minimum", value=current["spec_min"] if current else None,
                                   format="%.2f", placeholder="Blank = no lower limit")
        spec_max = f2.number_input("Maximum", value=current["spec_max"] if current else None,
                                   format="%.2f", placeholder="Blank = no upper limit")
        unit = f3.selectbox("Unit", UNITS,
                            index=UNITS.index(current["unit"]) if current else 0)
        reason = st.text_input("Reason for change" + (" *" if current else ""),
                               placeholder="e.g. Aligned with USP <711>")
        submitted = st.form_submit_button("Save specification", type="primary")

    if submitted:
        try:
            saved = services.save_specification(
                sample_type, test_name, spec_min, spec_max, unit, user["username"],
                reason=reason, expected_version=current["version"] if current else None)
        except services.ServiceError as e:
            st.error(str(e))
        else:
            # Shown after the rerun, which refreshes the table above.
            st.session_state.spec_saved = (
                f"Saved {sample_type} × {test_name} as v{saved['version']}.")
            st.rerun()
