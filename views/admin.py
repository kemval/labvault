"""
pages/admin.py — Admin panel: user list and system info
Only accessible to users with role='admin'. Lab techs get a hard stop at the door.
"""

import streamlit as st
from db import get_all_users, get_all_samples, count_samples_by_status, count_oos_results


def show():
    # Page header — consistent with all other views
    st.markdown("""
        <div class="lv-header">
            <div><h1>⚙️ Admin Panel</h1>
            <span>System overview and user management</span></div>
        </div>
    """, unsafe_allow_html=True)

    user = st.session_state.user

    # Double-check the role here even though the sidebar already hides this page
    # from non-admins — defense in depth. Never trust just the UI to enforce access.
    if user["role"] != "admin":
        st.error("Access denied. Admin only.")
        return

    # ── SYSTEM STATS ─────────────────────────────────────────
    st.markdown("#### System Overview")
    samples    = get_all_samples()
    status_map = count_samples_by_status()
    oos        = count_oos_results()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Samples",    len(samples))
    c2.metric("Completed",        status_map.get("Completed", 0))
    c3.metric("OOS Results",      oos)
    # Quick count of how many samples came from the FDA import vs. manual entry
    c4.metric("FDA-Imported",     len([s for s in samples if s.get("source") == "FDA"]))

    st.markdown("---")

    # ── USER LIST ────────────────────────────────────────────
    # Show who's in the system with color-coded role badges —
    # red for admin, blue for lab tech. Simple but effective.
    st.markdown("#### Registered Users")
    users = get_all_users()
    for u in users:
        role_badge = "🔴 Admin" if u["role"] == "admin" else "🔵 Lab Tech"
        st.markdown(f"- **{u['username']}** — {role_badge}")

    st.markdown("---")
    st.markdown("#### Default Login Credentials")
    # Displayed in a code block so it's easy to copy — just for demo convenience
    st.code("""
Admin     →  username: admin    password: admin123
Lab Tech  →  username: kembly   password: lab2024
Lab Tech  →  username: carlos   password: lab2024
Lab Tech  →  username: maria    password: lab2024
    """)

    # A gentle reminder that adding users requires a code change for now.
    # In a real production system this would obviously be a full user management UI.
    st.info("To add new users, update the `seed_users()` function in `db.py` and re-run the app.")
