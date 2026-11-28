"""
pages/sample_tracking.py — View, filter, and update sample status
"""

import streamlit as st
from domain import PRIORITIES, PRIORITY_CRITICAL, PRIORITY_MAJOR, PRIORITY_MINOR, SAMPLE_STATUSES, assignee_options, may_edit, status_options
from db import get_all_samples, get_lab_techs
import services
from views.ui import esc, SIMULATED_LABEL, UNASSIGNED, page_header




def _form_keys(sample_id):
    return [f"status_{sample_id}", f"assign_{sample_id}", f"reason_{sample_id}",
            f"version_{sample_id}"]


def _request_reload(sample_id):
    st.session_state[f"reload_{sample_id}"] = True


def _form_version(s):
    """
    The version this session's edit form was initialised from. Streamlit
    reruns the script on every click and re-reads the sample, so the fresh
    row's version can't be used for the optimistic-concurrency check — the
    form widgets still hold what the user first saw. Store that version next
    to them and reset both together on reload.
    """
    sid = s["sample_id"]
    if st.session_state.pop(f"reload_{sid}", False):
        for key in _form_keys(sid):
            st.session_state.pop(key, None)
    return st.session_state.setdefault(f"version_{sid}", s["version"])


def show():
    page_header("🔬 Sample Tracking", "Monitor and update the status of all laboratory samples")

    user  = st.session_state.user
    techs = get_lab_techs()

    # ── FILTERS ──────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Filter by Status", ["All", *SAMPLE_STATUSES])
    with col2:
        priority_filter = st.selectbox("Filter by Priority", ["All", *PRIORITIES])
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
        priority_colors = {PRIORITY_CRITICAL: "#d32f2f", PRIORITY_MAJOR: "#f57c00", PRIORITY_MINOR: "#2e7d32"}
        border_color = priority_colors.get(s["priority"], "#1a4a8a")

        with st.expander(
            f"🔬 {s['sample_id']}  ·  {s['product_name'][:60]}  ·  [{s['status']}]"
            + (f"  ·  {SIMULATED_LABEL}" if s.get("is_simulated") else ""),
            expanded=False
        ):
            col_info, col_actions = st.columns([2, 1])

            with col_info:
                sim_line = ("<b>Data:</b> <span class='badge badge-sim'>SIMULATED</span> "
                            "FDA recall demo — lot, assignment and results are not real<br>"
                            if s.get("is_simulated") else "")
                st.markdown(f"""
                    <div style="background:#f8f9ff;border-radius:8px;padding:14px;
                                border-left:4px solid {border_color}">
                        <b>Product:</b> {esc(s['product_name'])}<br>
                        <b>Manufacturer:</b> {esc(s['manufacturer'])}<br>
                        <b>Lot Number:</b> {esc(s.get('lot_number') or 'N/A')}<br>
                        <b>Sample Type:</b> {esc(s['sample_type'])}<br>
                        <b>Classification:</b> {esc(s['recall_class'])}<br>
                        <b>Priority:</b> {esc(s['priority'])}<br>
                        <b>Collection Date:</b> {esc(s['collection_date'])}<br>
                        <b>Assigned To:</b> {esc(s['assigned_to'] or UNASSIGNED)}<br>
                        <b>Source:</b> {esc(s.get('source') or 'FDA')}<br>
                        <b>Reason:</b> {esc((s.get('reason_for_recall') or 'N/A')[:200])}<br>
                        {sim_line}
                    </div>
                """, unsafe_allow_html=True)

                if s.get("notes"):
                    st.markdown(f"**Notes:** {s['notes']}")

            with col_actions:
                st.markdown("**Update Sample**")
                if not may_edit(user, s):
                    # Read-only: the rules (domain.py, ADR 0011) are enforced by
                    # services.update_sample too — this just doesn't offer them.
                    st.caption(f"Assigned to **{s['assigned_to']}** — only the assignee "
                               "or an admin can change this sample.")
                    continue
                form_version = _form_version(s)
                if form_version != s["version"]:
                    st.warning("Someone else changed this sample after you opened it. "
                               "The details on the left are current; reload the form "
                               "before making changes.")
                    st.button("🔄 Reload form", key=f"reload_btn_{s['sample_id']}",
                              on_click=_request_reload, args=(s["sample_id"],))

                # Only the transitions this user may make are offered.
                new_status = st.selectbox(
                    "Status", status_options(user, s), index=0,
                    key=f"status_{s['sample_id']}",
                    help="Allowed next steps for your role. Completing needs every result "
                         "reviewed by a second person and at least one approved; "
                         "reopening is admin-only.")

                # Admins assign any lab tech; a tech can only claim an unassigned sample.
                names = [UNASSIGNED if a is None else a
                         for a in assignee_options(user, s, techs)]
                choice = st.selectbox("Assigned To", names, index=0,
                                      key=f"assign_{s['sample_id']}",
                                      disabled=len(names) == 1)
                new_assignee = None if choice == UNASSIGNED else choice

                reason = st.text_input(
                    "Reason for change *", key=f"reason_{s['sample_id']}",
                    placeholder="e.g. Analysis started; reassigned for workload",
                    help="Required for any change — recorded in the audit trail.")

                if st.button("💾 Save Changes", key=f"save_{s['sample_id']}", type="primary"):
                    # One transaction for both fields + their audit rows. The
                    # version is the one this form was opened with: if someone
                    # else saved in between, nothing is written.
                    try:
                        changed = services.update_sample(
                            s["sample_id"], form_version, user["username"],
                            status=new_status, assigned_to=new_assignee, reason=reason)
                    except services.ServiceError as e:
                        st.error(str(e))
                    else:
                        if changed:
                            _request_reload(s["sample_id"])  # form adopts the new version
                            st.rerun()
                        st.info("No changes to save.")
