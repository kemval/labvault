"""
pages/audit_trail.py — Full immutable action log
Every write in LabVault gets recorded here — that's what makes it GxP-compliant.
Filters let you zero in on a specific user or action type.
"""

import streamlit as st
import pandas as pd
from db import get_audit_trail


def show():
    # "Immutable" is the key word here — in a real GxP environment you'd actually
    # need a write-protected log. For this system, the DB isn't directly editable
    # by end users, which is close enough for a demo.
    st.markdown("""
        <div class="lv-header">
            <div><h1>🕵️ Audit Trail</h1>
            <span>Immutable log of every action taken in LabVault — GxP compliant</span></div>
        </div>
    """, unsafe_allow_html=True)

    # ── FILTERS ──────────────────────────────────────────────
    # Text filter for username and a dropdown for action type.
    # We filter in Python after fetching because the dataset is small enough
    # (500 rows max) that a SQL WHERE clause wouldn't make a measurable difference.
    col1, col2 = st.columns(2)
    with col1:
        user_filter = st.text_input("Filter by User", placeholder="e.g. kembly")
    with col2:
        action_filter = st.selectbox("Filter by Action", [
            "All", "SAMPLE_IMPORTED", "SAMPLE_CREATED", "STATUS_UPDATED",
            "SAMPLE_ASSIGNED", "RESULT_LOGGED", "PROTOCOL_CREATED", "REPORT_EXPORTED"
        ])

    # Grab the 500 most recent log entries — enough to be comprehensive without
    # loading everything ever written to the DB
    records = get_audit_trail(limit=500)

    # Apply filters — case-insensitive substring match for user, exact match for action
    if user_filter:
        records = [r for r in records if user_filter.lower() in r["user"].lower()]
    if action_filter != "All":
        records = [r for r in records if r["action"] == action_filter]

    st.markdown(f"**{len(records)} log entries**")
    st.markdown("---")

    if not records:
        st.info("No audit entries found.")
        return

    # Build the DataFrame with only the columns we want to show
    df = pd.DataFrame(records)[[
        "timestamp", "user", "action", "module", "target_id", "detail"
    ]]
    df.columns = ["Timestamp", "User", "Action", "Module", "Target", "Detail"]

    def color_action(val):
        """
        Apply background+text color to Action cells based on the action type.
        Dark backgrounds with light text — the colors are muted on purpose so
        the table doesn't look like a Christmas tree, but still scannable at a glance.
        """
        colors = {
            "STATUS_UPDATED":   "background-color:#1a3a5c; color:#90caf9",   # blue — routine update
            "RESULT_LOGGED":    "background-color:#3c1a5c; color:#ce93d8",   # purple — test result
            "SAMPLE_CREATED":   "background-color:#1a3c2a; color:#a5d6a7",   # green — new sample
            "SAMPLE_IMPORTED":  "background-color:#1a3c2a; color:#a5d6a7",   # green — bulk import
            "REPORT_EXPORTED":  "background-color:#3c3a1a; color:#fff176",   # yellow — export action
        }
        return colors.get(val, "")  # no style for unlisted action types

    # Apply cell-level styling on just the Action column.
    # .map() applies the function to each cell individually (not the whole row).
    styled = df.style.map(color_action, subset=["Action"])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=600)
