"""
pages/admin.py — Admin panel: user list and system info
Only accessible to users with role='admin'. Lab techs get a hard stop at the door.
"""

import streamlit as st
from config import demo_mode
from db import get_all_users, get_all_samples, count_samples_by_status, count_oos_results, DEMO_USERS


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

    # Demo credentials are public by design — only shown on demo instances.
    if demo_mode():
        st.markdown("---")
        st.markdown("#### Demo Login Credentials")
        label = {"admin": "Admin", "lab_tech": "Lab Tech"}
        st.code("\n".join(
            f"{label[r]:<9} →  username: {u:<8} password: {p}" for u, p, r in DEMO_USERS
        ))

    # There is no user-management UI yet (roadmap item 3.6).
    st.info("User management is not available in the app yet. Accounts are created "
            "on first start only — see the Configuration section of the README.")
