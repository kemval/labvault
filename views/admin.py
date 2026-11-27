"""
pages/admin.py — Admin panel: user list and system info
Only accessible to users with role='admin'. Lab techs get a hard stop at the door.
"""

import streamlit as st
from domain import ROLE_ADMIN, ROLE_LAB_TECH, ROLE_SYSTEM, SOURCE_FDA, STATUS_COMPLETED
from views.ui import page_header
from config import demo_mode
from db import get_all_users, get_all_samples, count_samples_by_status, count_oos_results
from repo.users import DEMO_USERS


def show():
    # Page header — consistent with all other views
    page_header("⚙️ Admin Panel", "System overview and user management")

    user = st.session_state.user

    # Double-check the role here even though the sidebar already hides this page
    # from non-admins — defense in depth. Never trust just the UI to enforce access.
    if user["role"] != ROLE_ADMIN:
        st.error("Access denied. Admin only.")
        return

    # ── SYSTEM STATS ─────────────────────────────────────────
    st.markdown("#### System Overview")
    samples    = get_all_samples()
    status_map = count_samples_by_status()
    oos        = count_oos_results()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Samples",    len(samples))
    c2.metric("Completed",        status_map.get(STATUS_COMPLETED, 0))
    c3.metric("OOS Results",      oos)
    # Quick count of how many samples came from the FDA import vs. manual entry
    c4.metric("FDA-Imported",     len([s for s in samples if s.get("source") == SOURCE_FDA]))

    st.markdown("---")

    # ── USER LIST ────────────────────────────────────────────
    # Show who's in the system with color-coded role badges —
    # red for admin, blue for lab tech. Simple but effective.
    st.markdown("#### Registered Users")
    users = get_all_users()
    for u in users:
        role_badge = {ROLE_ADMIN: "🔴 Admin", ROLE_LAB_TECH: "🔵 Lab Tech",
                      ROLE_SYSTEM: "⚪ System (cannot log in)"}.get(u["role"], u["role"])
        st.markdown(f"- **{u['username']}** — {role_badge}")

    # Demo credentials are public by design — only shown on demo instances.
    if demo_mode():
        st.markdown("---")
        st.markdown("#### Demo Login Credentials")
        label = {ROLE_ADMIN: "Admin", ROLE_LAB_TECH: "Lab Tech"}
        st.code("\n".join(
            f"{label[r]:<9} →  username: {u:<8} password: {p}" for u, p, r in DEMO_USERS
        ))

    # There is no user-management UI yet (roadmap item 3.6).
    st.info("User management is not available in the app yet. Accounts are created "
            "on first start only — see the Configuration section of the README.")
