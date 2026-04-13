"""
pages/audit_trail.py — Full immutable action log
"""

import streamlit as st
import pandas as pd
from db import get_audit_trail


def show():
    st.markdown("""
        <div class="lv-header">
            <div><h1>🕵️ Audit Trail</h1>
            <span>Immutable log of every action taken in LabVault — GxP compliant</span></div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        user_filter = st.text_input("Filter by User", placeholder="e.g. kembly")
    with col2:
        action_filter = st.selectbox("Filter by Action", [
            "All", "SAMPLE_IMPORTED", "SAMPLE_CREATED", "STATUS_UPDATED",
            "SAMPLE_ASSIGNED", "RESULT_LOGGED", "PROTOCOL_CREATED", "REPORT_EXPORTED"
        ])

    records = get_audit_trail(limit=500)

    if user_filter:
        records = [r for r in records if user_filter.lower() in r["user"].lower()]
    if action_filter != "All":
        records = [r for r in records if r["action"] == action_filter]

    st.markdown(f"**{len(records)} log entries**")
    st.markdown("---")

    if not records:
        st.info("No audit entries found.")
        return

    df = pd.DataFrame(records)[[
        "timestamp", "user", "action", "module", "target_id", "detail"
    ]]
    df.columns = ["Timestamp", "User", "Action", "Module", "Target", "Detail"]

    def color_action(val):
        colors = {
            "STATUS_UPDATED":   "background-color:#1a3a5c; color:#90caf9",
            "RESULT_LOGGED":    "background-color:#3c1a5c; color:#ce93d8",
            "SAMPLE_CREATED":   "background-color:#1a3c2a; color:#a5d6a7",
            "SAMPLE_IMPORTED":  "background-color:#1a3c2a; color:#a5d6a7",
            "REPORT_EXPORTED":  "background-color:#3c3a1a; color:#fff176",
        }
        return colors.get(val, "")

    styled = df.style.map(color_action, subset=["Action"])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=600)
