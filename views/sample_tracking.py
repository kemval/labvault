"""
views/sample_tracking.py — find samples, then view and update one at a time.

Filtering, sorting and paging run in SQL (repo.samples.find_samples), so the
page draws one table page plus one detail panel however many samples exist
(audit M2/U3, ADR 0016).
"""

import pandas as pd
import streamlit as st

from domain import (PRIORITIES, PRIORITY_CRITICAL, PRIORITY_MAJOR, PRIORITY_MINOR,
                    SAMPLE_STATUSES, TERMINAL_STATUSES, assignee_options, may_edit,
                    status_options)
from db import find_samples, get_lab_techs, get_sample_detail
import services
from views.ui import esc, html_block, SIMULATED_LABEL, UNASSIGNED, page_header, simulated_text

PAGE_SIZE = 25

SHOW_ALL, SHOW_MINE, SHOW_UNASSIGNED = "All samples", "Assigned to me", "Unassigned"
SORTS = {"Newest first": "newest", "Priority (Critical first)": "priority",
         "Collection date (oldest first)": "collection", "Sample ID": "sample_id"}
FILTER_KEYS = ("trk_status", "trk_priority", "trk_search", "trk_show", "trk_sort")


def _form_keys(sample_id):
    return [f"status_{sample_id}", f"assign_{sample_id}", f"reason_{sample_id}",
            f"confirm_{sample_id}", f"version_{sample_id}"]


def _request_reload(sample_id):
    st.session_state[f"reload_{sample_id}"] = True


def _first_page():
    st.session_state["trk_page"] = 1


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


def _filters(user):
    """The filter row; returns the find_samples arguments it selects."""
    col1, col2, col3 = st.columns(3)
    with col1:
        status = st.selectbox("Filter by Status", ["All", *SAMPLE_STATUSES],
                              key="trk_status", on_change=_first_page)
    with col2:
        priority = st.selectbox("Filter by Priority", ["All", *PRIORITIES],
                                key="trk_priority", on_change=_first_page)
    with col3:
        search = st.text_input("Search by Sample ID or Product", key="trk_search",
                               placeholder="e.g. D-0318 or Metformin", on_change=_first_page)
    col4, col5 = st.columns([2, 1])
    with col4:
        show = st.radio("Show", [SHOW_ALL, SHOW_MINE, SHOW_UNASSIGNED], horizontal=True,
                        key="trk_show", on_change=_first_page)
    with col5:
        sort = st.selectbox("Sort by", list(SORTS), key="trk_sort", on_change=_first_page)
    return {"status": None if status == "All" else status,
            "priority": None if priority == "All" else priority,
            "search": search,
            "assigned_to": user["username"] if show == SHOW_MINE else None,
            "unassigned": show == SHOW_UNASSIGNED,
            "sort": SORTS[sort]}


def _table(rows):
    st.dataframe(pd.DataFrame([{
        "Sample ID": r["sample_id"], "Product": r["product_name"], "Status": r["status"],
        "Priority": r["priority"], "Assigned To": r["assigned_to"] or UNASSIGNED,
        "Collected": r["collection_date"], "Type": r["sample_type"],
        "Simulated": simulated_text(r["is_simulated"]),
    } for r in rows]), hide_index=True, width="stretch")


def show():
    page_header("🔬 Sample Tracking", "Find a sample, then open it to view or update it")

    user = st.session_state.user
    args = _filters(user)

    total = find_samples(**args, limit=0)[1]
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(st.session_state.get("trk_page", 1), pages)
    st.session_state["trk_page"] = page
    rows, total = find_samples(**args, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)

    if flash := st.session_state.pop("trk_flash", None):
        st.success(flash)

    if not rows:
        st.info("No samples match your filters.")
        return

    first = (page - 1) * PAGE_SIZE + 1
    st.markdown(f"**{total:,} sample(s) found** · showing {first:,}–{first + len(rows) - 1:,}")
    _table(rows)
    if pages > 1:
        st.number_input(f"Page (of {pages:,})", min_value=1, max_value=pages, step=1,
                        key="trk_page")

    # Only samples on this page can be opened; a stale choice is dropped
    # rather than left pointing at a row the user can no longer see.
    ids = [r["sample_id"] for r in rows]
    if st.session_state.get("trk_open") not in ids:
        st.session_state.pop("trk_open", None)
    labels = {r["sample_id"]: f"{r['sample_id']} · {r['product_name'][:60]}" for r in rows}
    sid = st.selectbox("Open sample", ids, index=None, key="trk_open",
                       format_func=labels.get, placeholder="Choose a sample from this page")
    st.markdown("---")
    if sid is None:
        st.caption("Choose a sample above to see its details and update it.")
        return
    s = get_sample_detail(sid)
    if s is None:
        st.warning("That sample no longer exists.")
        return
    _detail(user, s)


def _detail(user, s):
    priority_colors = {PRIORITY_CRITICAL: "#d32f2f", PRIORITY_MAJOR: "#f57c00",
                       PRIORITY_MINOR: "#2e7d32"}
    border_color = priority_colors.get(s["priority"], "#1a4a8a")
    st.subheader(f"🔬 {s['sample_id']}"
                 + (f"  ·  {SIMULATED_LABEL}" if s.get("is_simulated") else ""))
    col_info, col_actions = st.columns([2, 1])

    with col_info:
        sim_line = ("<b>Data:</b> <span class='badge badge-sim'>SIMULATED</span> "
                    "FDA recall demo — lot, assignment and results are not real<br>"
                    if s.get("is_simulated") else "")
        protocol = (f"{s['protocol_name']} (#{s['protocol_id']})"
                    if s.get("protocol_id") else "None assigned")
        html_block(f"""
            <div style="background:#f8f9ff;border-radius:8px;padding:14px;
                        border-left:4px solid {border_color}">
                <b>Product:</b> {esc(s['product_name'])}<br>
                <b>Status:</b> {esc(s['status'])}<br>
                <b>Manufacturer:</b> {esc(s['manufacturer'])}<br>
                <b>Lot Number:</b> {esc(s.get('lot_number') or 'N/A')}<br>
                <b>Sample Type:</b> {esc(s['sample_type'])}<br>
                <b>Protocol:</b> {esc(protocol)}<br>
                <b>Classification:</b> {esc(s['recall_class'])}<br>
                <b>Priority:</b> {esc(s['priority'])}<br>
                <b>Collection Date:</b> {esc(s['collection_date'])}<br>
                <b>Assigned To:</b> {esc(s['assigned_to'] or UNASSIGNED)}<br>
                <b>Results:</b> {s['result_count']} logged, {s['approved_count']} approved,
                    {s['unreviewed_count']} awaiting review<br>
                <b>Source:</b> {esc(s.get('source') or 'FDA')}<br>
                <b>Reason:</b> {esc((s.get('reason_for_recall') or 'N/A')[:200])}<br>
                {sim_line}
            </div>
        """)
        if s.get("notes"):
            st.markdown("**Notes:**")
            st.text(s["notes"])

    with col_actions:
        st.markdown("**Update Sample**")
        if not may_edit(user, s):
            # Read-only: the rules (domain.py, ADR 0011) are enforced by
            # services.update_sample too — this just doesn't offer them.
            st.caption(f"Assigned to **{s['assigned_to']}** — only the assignee "
                       "or an admin can change this sample.")
            return
        _edit_form(user, s)


def _edit_form(user, s):
    sid = s["sample_id"]
    form_version = _form_version(s)
    if form_version != s["version"]:
        st.warning("Someone else changed this sample after you opened it. "
                   "The details on the left are current; reload the form "
                   "before making changes.")
        st.button("🔄 Reload form", key=f"reload_btn_{sid}",
                  on_click=_request_reload, args=(sid,))

    # Only the transitions this user may make are offered.
    new_status = st.selectbox(
        "Status", status_options(user, s), index=0, key=f"status_{sid}",
        help="Allowed next steps for your role. Completing needs every result "
             "reviewed by a second person and at least one approved; "
             "reopening is admin-only.")

    # Admins assign any lab tech; a tech can only claim an unassigned sample.
    names = [UNASSIGNED if a is None else a
             for a in assignee_options(user, s, get_lab_techs())]
    choice = st.selectbox("Assigned To", names, index=0, key=f"assign_{sid}",
                          disabled=len(names) == 1)
    new_assignee = None if choice == UNASSIGNED else choice

    reason = st.text_input(
        "Reason for change *", key=f"reason_{sid}",
        placeholder="e.g. Analysis started; reassigned for workload",
        help="Required for any change — recorded in the audit trail.")

    # Rejecting or completing ends the sample's lifecycle (only an admin can
    # reopen it), so it takes an explicit confirmation (audit U7).
    confirmed = True
    if new_status != s["status"] and new_status in TERMINAL_STATUSES:
        confirmed = st.checkbox(f"I confirm {sid} should be marked **{new_status}**",
                                key=f"confirm_{sid}")

    if st.button("💾 Save Changes", key=f"save_{sid}", type="primary", disabled=not confirmed):
        # One transaction for both fields + their audit rows. The version is
        # the one this form was opened with: if someone else saved in
        # between, nothing is written.
        try:
            changed = services.update_sample(
                sid, form_version, user["username"],
                status=new_status, assigned_to=new_assignee, reason=reason)
        except services.ServiceError as e:
            st.error(str(e))
        else:
            if changed:
                _request_reload(sid)  # form adopts the new version
                st.session_state["trk_flash"] = f"Saved changes to {sid}."
                st.rerun()
            st.info("No changes to save.")


if __name__ == "__main__":     # run as a page by st.navigation (views/navigation.py)
    show()
