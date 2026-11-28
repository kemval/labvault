"""
pages/test_results.py — Log and view test results, OOS flagging
"""

import streamlit as st
from domain import (OUTCOMES, QUALITATIVE_TESTS, RESULT_OOS, RESULT_PASS, RESULT_STATUSES,
                    REVIEW_AWAITING, REVIEW_MEANINGS, SIGNATURE_MEANING_TEXT, STATUS_IN_PROGRESS,
                    TEST_TYPES, result_entry_error, review_error)
import pandas as pd
from datetime import date
from db import (get_all_samples, get_all_specifications, get_results_awaiting_review,
                get_results_for_sample)
import services
from views.ui import simulated_text, SIMULATED_LABEL, page_header


def _fmt(value):
    return "—" if value is None else f"{value:g}"


def _log_result_tab(user, samples):
    # Only In Progress samples assigned to this user (any, for admins);
    # services.record_result enforces the same rule (ADR 0011).
    open_samples = {
        f"{s['sample_id']} — {s['product_name'][:50]}"
        + (f" ({SIMULATED_LABEL})" if s.get("is_simulated") else ""): s
        for s in samples if result_entry_error(user, s) is None}
    if not open_samples:
        st.info("No samples are open for results. Results can be logged on "
                "**In Progress** samples assigned to you — start one in Sample Tracking.")
        return

    st.markdown("#### New Test Result Entry")
    # Outside the form so the specification shown follows the selection.
    c1, c2 = st.columns(2)
    sample = open_samples[c1.selectbox("Select Sample *", list(open_samples), key="result_sample")]
    test_name = c2.selectbox("Test Name *", TEST_TYPES, key="result_test")
    qualitative = test_name in QUALITATIVE_TESTS

    if qualitative:
        st.caption(f"{test_name} is a pass/fail test — record the outcome.")
    else:
        spec = next((x for x in get_all_specifications()
                     if x["sample_type"] == sample["sample_type"]
                     and x["test_name"] == test_name), None)
        if spec is None:
            st.warning(f"No specification is defined for **{test_name}** on "
                       f"**{sample['sample_type']}** samples, so this result can't be logged. "
                       "Ask an admin to add one on the Specifications page.")
            return
        st.info(f"Specification v{spec['version']} ({sample['sample_type']}): "
                f"{_fmt(spec['spec_min'])} to {_fmt(spec['spec_max'])} {spec['unit']} — "
                "set by QA, not editable here.")

    with st.form("result_form", clear_on_submit=True):
        f1, f2 = st.columns(2)
        if qualitative:
            outcome = f1.selectbox("Outcome *", ["—", *OUTCOMES])
            result_value = None
        else:
            result_value = f1.number_input(f"Result Value * ({spec['unit']})", value=None,
                                           format="%.2f")
            outcome = "—"
        tested_at = f2.date_input("Test Date", value=date.today())
        notes = st.text_area("Notes / Observations",
                             placeholder="e.g. Sample appeared discolored prior to testing...")
        submitted = st.form_submit_button("Submit Result", type="primary",
                                          use_container_width=True)

    if submitted:
        # The service looks up the specification again and decides the status.
        try:
            saved = services.record_result({
                "sample_id":    sample["sample_id"],
                "test_name":    test_name,
                "result_value": result_value,
                "outcome":      None if outcome == "—" else outcome,
                "tested_at":    tested_at.strftime("%Y-%m-%d"),
                "notes":        notes,
            }, user["username"])
        except services.ServiceError as e:
            st.error(str(e))
            st.warning("Nothing was saved.")
            return

        if saved["status"] == RESULT_OOS:
            st.error(f"🚨 OOS RESULT: {test_name} = {saved['shown']} — Outside specification. "
                     "Deviation review required.")
        else:
            st.success(f"✅ Result logged: {test_name} = {saved['shown']} — **{saved['status']}**")


def _review_text(r):
    if not r.get("review"):
        # Only results on In Progress samples can still be signed; others
        # (e.g. completed before e-signatures existed) stay unreviewed.
        return REVIEW_AWAITING if r["sample_status"] == STATUS_IN_PROGRESS else "Not reviewed"
    text = f"{r['review']} by {r['reviewed_by']}"
    return f"{text}: {r['review_reason']}" if r.get("review_reason") else text


def _review_tab(user):
    """Second-person review with e-signature (ADR 0014)."""
    if "review_signed" in st.session_state:
        st.success(st.session_state.pop("review_signed"))
    awaiting = get_results_awaiting_review()
    queue = [r for r in awaiting if review_error(user, r) is None]
    own = sum(r["tested_by"] == user["username"] for r in awaiting)
    if own:
        st.caption(f"{own} result(s) you logged are awaiting someone else's review.")
    if not queue:
        st.info("Nothing for you to review. Results on In Progress samples appear here "
                "once logged — except your own, which need a second person.")
        return

    labels = {f"#{r['id']} · {r['sample_id']} · {r['test_name']} · {r['status']} "
              f"(by {r['tested_by']})": r for r in queue}
    r = labels[st.selectbox("Result to review", list(labels), key="review_result")]
    shown = (f"{_fmt(r['result_value'])} {r['result_unit']}" if r["result_value"] is not None
             else "pass/fail outcome")
    limits = ("" if r["spec_min"] is None and r["spec_max"] is None
              else f" · spec {_fmt(r['spec_min'])} to {_fmt(r['spec_max'])}")
    st.markdown(f"**{r['product_name'][:60]}** ({r['sample_type']}) — {r['test_name']}: "
                f"**{shown}**{limits} → **{r['status']}**  \n"
                f"Tested by {r['tested_by']} on {r['tested_at']}"
                + (f" · Notes: {r['notes']}" if r.get("notes") else ""))

    with st.form("review_form", clear_on_submit=True):
        meaning = st.radio("Meaning of your signature *", REVIEW_MEANINGS, index=None,
                           format_func=SIGNATURE_MEANING_TEXT.get)
        reason = st.text_input("Reason (required to reject)")
        password = st.text_input("Your password *", type="password")
        st.caption(f"Signing as **{user['username']}**. Your name, the meaning and the time "
                   "are recorded permanently with the result.")
        submitted = st.form_submit_button("Sign", type="primary")

    if submitted:
        if meaning is None:
            st.error("Choose the meaning of your signature.")
            return
        try:
            saved = services.sign_result(r["id"], user["username"], password, meaning, reason)
        except services.ServiceError as e:
            st.error(str(e))
            return
        st.session_state.review_signed = (
            f"Signed result #{r['id']}: {meaning} ({saved['signed_at']} UTC).")
        st.rerun()


def show():
    page_header("📋 Test Results", "Log results, review and sign them, and see Out-of-Spec findings")

    user    = st.session_state.user
    samples = get_all_samples()

    if not samples:
        st.info("No samples in the system yet. Import FDA data or register a sample first.")
        return

    tab_log, tab_review, tab_view = st.tabs(
        ["📝 Log New Result", "✍️ Review", "📊 View All Results"])

    # ── LOG NEW RESULT ────────────────────────────────────────
    with tab_log:
        _log_result_tab(user, samples)

    # ── REVIEW (E-SIGNATURE) ──────────────────────────────────
    with tab_review:
        _review_tab(user)

    # ── VIEW ALL RESULTS ──────────────────────────────────────
    with tab_view:
        st.markdown("#### All Test Results")

        filter_status = st.selectbox("Filter", ["All", *RESULT_STATUSES])

        # Gather all results across all samples
        all_results = []
        for s in samples:
            for r in get_results_for_sample(s["sample_id"]):
                r["product_name"] = s["product_name"][:50]
                r["sample_status"] = s["status"]
                all_results.append(r)

        if filter_status != "All":
            all_results = [r for r in all_results if r["status"] == filter_status]

        if not all_results:
            st.info("No results found.")
            return

        for r in all_results:
            r["review_text"] = _review_text(r)
        df = pd.DataFrame(all_results)[[
            "sample_id", "product_name", "test_name",
            "result_value", "result_unit", "spec_min", "spec_max",
            "status", "review_text", "spec_version", "tested_by", "tested_at", "is_simulated"
        ]]
        df["is_simulated"] = df["is_simulated"].map(simulated_text)
        # Which specification version judged the result; older results keep
        # the limits typed at the time (ADR 0012).
        df["spec_version"] = df["spec_version"].map(
            lambda v: "as recorded" if pd.isna(v) else f"v{int(v)}")
        df.columns = [
            "Sample ID", "Product", "Test",
            "Result", "Unit", "Spec Min", "Spec Max",
            "Status", "Review", "Spec", "Tested By", "Date", "Simulated"
        ]

        # Color OOS rows
        def color_status(val):
            if val == RESULT_OOS:
                return "background-color: #fce4ec; color: #c62828; font-weight: 600"
            elif val == RESULT_PASS:
                return "background-color: #e8f5e9; color: #2e7d32; font-weight: 600"
            return ""

        styled = df.style.map(color_status, subset=["Status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
