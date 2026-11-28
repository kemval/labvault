"""
views/investigations.py — OOS investigations (ADR 0015). Every OOS result
opens one; everyone can read them, and an admin (QA) closes each with an
e-signature. The conclusion decides how the result may then be signed.
"""

import pandas as pd
import streamlit as st

import services
from db import get_all_investigations
from domain import CONCLUSION_TEXT, CONCLUSIONS, INVESTIGATION_OPEN, investigation_error
from views.ui import page_header, simulated_text


def _fmt(value):
    return "—" if value is None or pd.isna(value) else f"{value:g}"


def _summary(i):
    return (f"{i['test_name']}: {_fmt(i['result_value'])} {i['result_unit']} "
            f"(spec {_fmt(i['spec_min'])} to {_fmt(i['spec_max'])})")


def show():
    page_header("🔎 OOS Investigations",
                "Every out-of-specification result is investigated before it can be signed")
    user = st.session_state.user
    if "investigation_closed" in st.session_state:
        st.success(st.session_state.pop("investigation_closed"))

    rows = get_all_investigations()
    open_ones = [i for i in rows if i["status"] == INVESTIGATION_OPEN]
    c1, c2 = st.columns(2)
    c1.metric("Open", len(open_ones))
    c2.metric("Closed", len(rows) - len(open_ones))
    if not rows:
        st.info("No OOS investigations yet. One opens automatically for every OOS result.")
        return

    df = pd.DataFrame([{
        "#": i["id"], "Sample": i["sample_id"], "Product": i["product_name"][:40],
        "Result": _summary(i), "Analyst": i["tested_by"], "Opened (UTC)": i["opened_at"],
        "Status": i["status"], "Conclusion": i["conclusion"] or "—",
        "Findings": i["findings"] or "", "Closed By": i["closed_by"] or "",
        "Simulated": simulated_text(i["is_simulated"]),
    } for i in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)

    closable = [i for i in open_ones if investigation_error(user, i) is None]
    if not closable:
        if open_ones:
            st.caption("Only an admin (QA) can close an investigation, and never one on "
                       "a result they logged.")
        return

    st.markdown("---")
    st.markdown("#### Close an investigation")
    labels = {f"#{i['id']} · {i['sample_id']} · {_summary(i)} (by {i['tested_by']})": i
              for i in closable}
    chosen = labels[st.selectbox("Investigation", list(labels), key="investigation_pick")]
    with st.form("investigation_form", clear_on_submit=True):
        conclusion = st.radio("Conclusion *", CONCLUSIONS, index=None,
                              format_func=CONCLUSION_TEXT.get)
        findings = st.text_area("Findings *", placeholder="What was checked (calculations, "
                                "instrument, standards, sample prep) and what was found")
        password = st.text_input("Your password *", type="password")
        st.caption(f"Signing as **{user['username']}**. Your name, the conclusion and the time "
                   "are recorded permanently; a closed investigation can't be changed.")
        submitted = st.form_submit_button("Close investigation", type="primary")

    if submitted:
        if conclusion is None:
            st.error("Choose a conclusion.")
            return
        try:
            saved = services.close_investigation(chosen["id"], user["username"], password,
                                                 conclusion, findings)
        except services.ServiceError as e:
            st.error(str(e))
            return
        st.session_state.investigation_closed = (
            f"Closed investigation #{chosen['id']}: {saved['conclusion']} "
            f"({saved['closed_at']} UTC).")
        st.rerun()


if __name__ == "__main__":     # run as a page by st.navigation (views/navigation.py)
    show()
