"""
pages/protocols.py — View and create GxP test protocols
Protocols define the step-by-step procedures a lab tech should follow when testing a sample.
Admins can create new ones; all users can browse existing protocols.
"""

import streamlit as st
from datetime import datetime
from db import get_all_protocols, insert_protocol, log_action

# The complete list of sample types we support — used both here and in sample_intake.
# Keeping this in sync with what detect_sample_type() returns in seed.py matters
# because protocols are matched to samples by sample_type.
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

    # Two tabs: one for browsing, one for creating.
    # Separating read and write actions into tabs keeps the UI clean.
    tab_view, tab_create = st.tabs(["📋 View Protocols", "➕ Create Protocol"])

    with tab_view:
        if not protocols:
            st.info("No protocols yet.")
            return

        # Each protocol gets an expandable section — shows metadata at a glance
        # and opens to reveal the full step-by-step procedure
        for p in protocols:
            with st.expander(f"📄 {p['name']}  ·  [{p['sample_type']}]"):
                st.markdown(f"**Description:** {p['description']}")
                st.markdown(f"**Applicable Sample Type:** `{p['sample_type']}`")
                st.markdown(f"**Created by:** {p['created_by']}  ·  {p['created_at']}")
                st.markdown("**Procedure Steps:**")
                # Steps are stored as a single newline-separated string in the DB
                steps = p["steps"].split("\n") if p.get("steps") else []
                for step in steps:
                    if step.strip():
                        # Non-breaking space for visual indent — keeps steps from
                        # sitting flush against the left edge
                        st.markdown(f"&nbsp;&nbsp;{step.strip()}")

    with tab_create:
        # Only admins can write new protocols — lab techs can view and follow them,
        # but they shouldn't be defining the procedures themselves
        if user["role"] != "admin":
            st.warning("Only administrators can create protocols.")
            return

        # clear_on_submit=True empties the form after a successful submission,
        # so the admin doesn't have to manually clear each field
        with st.form("protocol_form", clear_on_submit=True):
            st.markdown("#### New Protocol")
            name        = st.text_input("Protocol Name *")
            sample_type = st.selectbox("Applicable Sample Type", SAMPLE_TYPES)
            description = st.text_area("Description")
            steps       = st.text_area("Procedure Steps (one per line)",
                                       placeholder="1. Prepare samples\n2. Set equipment\n3. Measure...")

            submitted = st.form_submit_button("Create Protocol", type="primary", use_container_width=True)

        # Handle submission outside the form block — Streamlit requires this
        if submitted:
            if not name:
                st.error("Protocol name is required.")
                return

            insert_protocol({
                "name":        name,
                "sample_type": sample_type,
                "description": description,
                "steps":       steps,        # raw newline-separated text, stored as-is
                "created_by":  user["username"],
                "created_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            # Log the creation so there's a record of who added this protocol and when
            log_action(user["username"], "PROTOCOL_CREATED", "Protocols",
                       name, f"New protocol: {name} for {sample_type}")
            st.success(f"✅ Protocol '{name}' created.")
