"""
pages/sample_tracking.py — View, filter, and update sample status
"""

import streamlit as st
import pandas as pd
from db import get_all_samples, update_sample_status, update_sample_assignment, get_lab_techs, log_action


STATUS_OPTIONS = ["Pending", "In Progress", "Completed", "Rejected"]


def show():
    st.markdown("""
        <div class="lv-header">
            <div><h1>🔬 Sample Tracking</h1>
            <span>Monitor and update the status of all laboratory samples</span></div>
        </div>
    """, unsafe_allow_html=True)

    user  = st.session_state.user
    techs = get_lab_techs()

    # ── FILTERS ──────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Filter by Status", ["All"] + STATUS_OPTIONS)
    with col2:
        priority_filter = st.selectbox("Filter by Priority", ["All", "Critical", "Major", "Minor"])
    with col3:
        search = st.text_input("Search by Sample ID or Product", placeholder="e.g. D-0318 or Metformin")

    samples = get_all_samples(status_filter if status_filter != "All" else None)

    # Apply priority filter
    if priority_filter != "All":
        samples = [s for s in samples if s.get("priority") == priority_filter]

    # Apply search
    if search:
        search_lower = search.lower()
        samples = [s for s in samples if
                   search_lower in s["sample_id"].lower() or
                   search_lower in s["product_name"].lower()]

    st.markdown(f"**{len(samples)} sample(s) found**")
    st.markdown("---")

    if not samples:
        st.info("No samples match your filters.")
        return

    # ── SAMPLE TABLE ─────────────────────────────────────────
    for s in samples:
        priority_colors = {"Critical": "#d32f2f", "Major": "#f57c00", "Minor": "#2e7d32"}
        border_color = priority_colors.get(s["priority"], "#1a4a8a")

        with st.expander(
            f"🔬 {s['sample_id']}  ·  {s['product_name'][:60]}  ·  [{s['status']}]",
            expanded=False
        ):
            col_info, col_actions = st.columns([2, 1])

            with col_info:
                st.markdown(f"""
                    <div style="background:#f8f9ff;border-radius:8px;padding:14px;
                                border-left:4px solid {border_color}">
                        <b>Product:</b> {s['product_name']}<br>
                        <b>Manufacturer:</b> {s['manufacturer']}<br>
                        <b>Lot Number:</b> {s.get('lot_number', 'N/A')}<br>
                        <b>Sample Type:</b> {s['sample_type']}<br>
                        <b>Classification:</b> {s['recall_class']}<br>
                        <b>Priority:</b> {s['priority']}<br>
                        <b>Collection Date:</b> {s['collection_date']}<br>
                        <b>Assigned To:</b> {s['assigned_to']}<br>
                        <b>Source:</b> {s.get('source', 'FDA')}<br>
                        <b>Reason:</b> {s.get('reason_for_recall','N/A')[:200]}<br>
                    </div>
                """, unsafe_allow_html=True)

                if s.get("notes"):
                    st.markdown(f"**Notes:** {s['notes']}")

            with col_actions:
                st.markdown("**Update Sample**")

                # Status update
                new_status = st.selectbox(
                    "Status", STATUS_OPTIONS,
                    index=STATUS_OPTIONS.index(s["status"]),
                    key=f"status_{s['sample_id']}"
                )

                # Reassign
                if techs:
                    new_assignee = st.selectbox(
                        "Assigned To", techs,
                        index=techs.index(s["assigned_to"]) if s["assigned_to"] in techs else 0,
                        key=f"assign_{s['sample_id']}"
                    )
                else:
                    new_assignee = s["assigned_to"]

                if st.button("💾 Save Changes", key=f"save_{s['sample_id']}", type="primary"):
                    if new_status != s["status"]:
                        update_sample_status(s["sample_id"], new_status, user["username"])
                    if new_assignee != s["assigned_to"]:
                        update_sample_assignment(s["sample_id"], new_assignee, user["username"])
                    st.success("Updated!")
                    st.rerun()
