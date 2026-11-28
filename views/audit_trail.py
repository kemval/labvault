"""
pages/audit_trail.py — the full audit trail, filtered and paged in SQL.

The trail is append-only: database triggers reject any UPDATE or DELETE
(migration 4, ADR 0008). Changes to a field record the old value, the new
value and the user's reason. Timestamps are UTC (entries written before
migration 4 kept the server's local time, as originally recorded).
"""

import math

import pandas as pd
import streamlit as st

from db import get_audit_actions, get_audit_page
from views.ui import page_header

PAGE_SIZE = 100

ACTION_COLORS = {
    "STATUS_UPDATED":  "background-color:#1a3a5c; color:#90caf9",   # blue — routine update
    "SAMPLE_ASSIGNED": "background-color:#1a3a5c; color:#90caf9",
    "RESULT_LOGGED":   "background-color:#3c1a5c; color:#ce93d8",   # purple — test result
    "SAMPLE_CREATED":  "background-color:#1a3c2a; color:#a5d6a7",   # green — new data
    "SAMPLE_IMPORTED": "background-color:#1a3c2a; color:#a5d6a7",
    "REPORT_EXPORTED": "background-color:#3c3a1a; color:#fff176",   # yellow — data leaving
    "LOGIN_FAILED":    "background-color:#5c1a1a; color:#ef9a9a",   # red — security
    "ACCOUNT_LOCKED":  "background-color:#5c1a1a; color:#ef9a9a",
}


def show():
    page_header("🕵️ Audit Trail", "Append-only record of every change, export and sign-in")

    col1, col2 = st.columns(2)
    with col1:
        user_filter = st.text_input("Filter by User", placeholder="e.g. kembly").strip()
    with col2:
        action_filter = st.selectbox("Filter by Action", ["All"] + get_audit_actions())
    action = "" if action_filter == "All" else action_filter

    _, total = get_audit_page(user_filter, action, limit=1, offset=0)
    st.markdown(f"**{total} log entries**")
    if not total:
        st.markdown("---")
        st.info("No audit entries found.")
        return

    pages = math.ceil(total / PAGE_SIZE)
    page = 1
    if pages > 1:
        page = st.number_input(f"Page (of {pages}, newest first)", min_value=1,
                               max_value=pages, value=1, step=1, key="audit_page")
    records, _ = get_audit_page(user_filter, action, limit=PAGE_SIZE,
                                offset=(page - 1) * PAGE_SIZE)
    st.markdown("---")

    df = pd.DataFrame(records)[[
        "timestamp", "user", "action", "module", "target_id",
        "old_value", "new_value", "reason", "detail",
    ]]
    df.columns = ["Timestamp", "User", "Action", "Module", "Target",
                  "Old Value", "New Value", "Reason", "Detail"]

    styled = df.style.map(lambda v: ACTION_COLORS.get(v, ""), subset=["Action"])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=600)
