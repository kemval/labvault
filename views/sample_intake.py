"""
pages/sample_intake.py — Register new samples manually
"""

import streamlit as st
from datetime import date
from db import insert_sample, get_all_protocols, get_lab_techs, log_action
import uuid


def show():
    st.markdown("""
        <div class="lv-header">
            <div><h1>🧫 Sample Intake</h1>
            <span>Register a new sample for laboratory testing</span></div>
        </div>
    """, unsafe_allow_html=True)

    user      = st.session_state.user
    protocols = get_all_protocols()
    techs     = get_lab_techs()

    proto_options = {f"{p['name']} ({p['sample_type']})": p["id"] for p in protocols}

    with st.form("intake_form", clear_on_submit=True):
        st.markdown("#### Sample Information")
        c1, c2 = st.columns(2)

        with c1:
            product_name = st.text_input("Product Name *", placeholder="e.g. Metformin HCl Tablets 500mg")
            manufacturer = st.text_input("Manufacturer / Source *", placeholder="e.g. Sun Pharmaceutical")
            lot_number   = st.text_input("Lot Number", placeholder="e.g. AB1234")
            sample_type  = st.selectbox("Sample Type", ["Tablet", "Capsule", "Injectable", "Liquid", "Topical", "Powder"])

        with c2:
            recall_class    = st.selectbox("Classification", ["Class I", "Class II", "Class III"])
            priority        = st.selectbox("Priority", ["Critical", "Major", "Minor"])
            collection_date = st.date_input("Collection Date", value=date.today())
            assigned_to     = st.selectbox("Assign To", techs if techs else ["kembly"])

        reason = st.text_area("Reason for Testing / Nonconformance", placeholder="Describe the reason this sample was submitted for testing...")
        proto_choice = st.selectbox("Assign Protocol", ["None"] + list(proto_options.keys()))
        notes = st.text_area("Additional Notes", placeholder="Any additional information...")

        submitted = st.form_submit_button("Register Sample", type="primary", use_container_width=True)

    if submitted:
        if not product_name or not manufacturer:
            st.error("Product name and manufacturer are required.")
            return

        sample_id = f"LV-{uuid.uuid4().hex[:8].upper()}"
        proto_id  = proto_options.get(proto_choice) if proto_choice != "None" else None

        insert_sample({
            "sample_id":         sample_id,
            "product_name":      product_name,
            "lot_number":        lot_number,
            "manufacturer":      manufacturer,
            "sample_type":       sample_type,
            "recall_class":      recall_class,
            "priority":          priority,
            "reason_for_recall": reason,
            "collection_date":   collection_date.strftime("%Y-%m-%d"),
            "status":            "Pending",
            "assigned_to":       assigned_to,
            "protocol_id":       proto_id,
            "notes":             notes,
            "source":            "Manual",
        })

        log_action(user["username"], "SAMPLE_CREATED", "Sample Intake",
                   sample_id, f"Registered: {product_name} | {manufacturer}")

        st.success(f"✅ Sample **{sample_id}** registered successfully and assigned to **{assigned_to}**.")
        st.info(f"Priority: **{priority}** | Classification: **{recall_class}** | Status: **Pending**")
