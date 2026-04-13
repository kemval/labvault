"""
pages/protocols.py — View and create GxP test protocols
"""

import streamlit as st
from datetime import datetime
from db import get_all_protocols, insert_protocol, log_action

SAMPLE_TYPES = ["Tablet", "Capsule", "Injectable", "Liquid", "Topical", "Powder", "Non-sterile"]


def show():
    st.markdown("""
        <div class="lv-header">
            <div><h1>📄 Protocols</h1>
            <span>Standard GxP test protocols linked to sample types</span></div>
        </div>
    """, unsafe_allow_html=True)

    user      = st.session_state.user
    protocols = get_all_protocols()

    tab_view, tab_create = st.tabs(["📋 View Protocols", "➕ Create Protocol"])

    with tab_view:
        if not protocols:
            st.info("No protocols yet.")
            return

        for p in protocols:
            with st.expander(f"📄 {p['name']}  ·  [{p['sample_type']}]"):
                st.markdown(f"**Description:** {p['description']}")
                st.markdown(f"**Applicable Sample Type:** `{p['sample_type']}`")
                st.markdown(f"**Created by:** {p['created_by']}  ·  {p['created_at']}")
                st.markdown("**Procedure Steps:**")
                steps = p["steps"].split("\n") if p.get("steps") else []
                for step in steps:
                    if step.strip():
                        st.markdown(f"&nbsp;&nbsp;{step.strip()}")

    with tab_create:
        if user["role"] != "admin":
            st.warning("Only administrators can create protocols.")
            return

        with st.form("protocol_form", clear_on_submit=True):
            st.markdown("#### New Protocol")
            name        = st.text_input("Protocol Name *")
            sample_type = st.selectbox("Applicable Sample Type", SAMPLE_TYPES)
            description = st.text_area("Description")
            steps       = st.text_area("Procedure Steps (one per line)",
                                       placeholder="1. Prepare samples\n2. Set equipment\n3. Measure...")

            submitted = st.form_submit_button("Create Protocol", type="primary", use_container_width=True)

        if submitted:
            if not name:
                st.error("Protocol name is required.")
                return

            insert_protocol({
                "name":        name,
                "sample_type": sample_type,
                "description": description,
                "steps":       steps,
                "created_by":  user["username"],
                "created_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            log_action(user["username"], "PROTOCOL_CREATED", "Protocols",
                       name, f"New protocol: {name} for {sample_type}")
            st.success(f"✅ Protocol '{name}' created.")
