"""
pages/admin.py — Admin panel: user list and system info
Only accessible to users with role='admin'. Lab techs get a hard stop at the door.
"""

import os

import pandas as pd
import streamlit as st

import services
from domain import (LOGIN_ROLES, OOS_INVALIDATED, MIN_PASSWORD_LENGTH, ROLE_ADMIN, ROLE_LAB_TECH, ROLE_SYSTEM,
                    SOURCE_FDA, STATUS_COMPLETED)
from repo import core
from repo.core import utc_now
from views.ui import page_header
from config import backup_replica, demo_mode
from db import get_all_users, count_samples_by_source, count_samples_by_status, get_oos_breakdown
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
    status_map = count_samples_by_status()
    oos        = get_oos_breakdown()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Samples",    sum(status_map.values()))
    c2.metric("Completed",        status_map.get(STATUS_COMPLETED, 0))
    c3.metric("OOS Results",      oos["counted"],
              help=f"Excludes {oos[OOS_INVALIDATED]} invalidated by a laboratory error.")
    # Quick count of how many samples came from the FDA import vs. manual entry
    c4.metric("FDA-Imported",     count_samples_by_source().get(SOURCE_FDA, 0))
    _storage_status()

    st.markdown("---")

    # ── ACCOUNTS (ADR 0017) ──────────────────────────────────
    st.markdown("#### Accounts")
    accounts = get_all_users()
    _account_table(accounts)
    _manage_account(user, [a for a in accounts
                           if a["role"] != ROLE_SYSTEM and a["username"] != user["username"]])
    _create_account(user)

    # Demo credentials are public by design — only shown on demo instances.
    if demo_mode():
        st.markdown("---")
        st.markdown("#### Demo Login Credentials")
        label = {ROLE_ADMIN: "Admin", ROLE_LAB_TECH: "Lab Tech"}
        st.code("\n".join(
            f"{label[r]:<9} →  username: {u:<8} password: {p}" for u, p, r in DEMO_USERS
        ))


def _storage_status():
    """Where the data lives and whether it is continuously backed up (ADR 0023)."""
    replica = backup_replica()
    where = f"Database file: `{os.path.abspath(core.DB_PATH)}`"
    if replica:
        st.caption(f"{where} · Continuous backup (Litestream) to `{replica}`")
    elif demo_mode():
        st.caption(f"{where} · No continuous backup: demo data, rebuilt on restart.")
    else:
        st.warning(f"{where}. **No continuous backup is configured.** Records can be lost "
                   "if this disk is lost. Run LabVault with `deploy/start.sh` "
                   "(see docs/operations/durable-storage.md).")


ROLE_LABELS = {ROLE_ADMIN: "Admin", ROLE_LAB_TECH: "Lab Tech",
               ROLE_SYSTEM: "System (cannot log in)"}


def _is_locked(a):
    return bool(a["locked_until"]) and a["locked_until"] > utc_now()


def _account_table(accounts):
    st.dataframe(pd.DataFrame([{
        "Username": a["username"], "Role": ROLE_LABELS.get(a["role"], a["role"]),
        "Status": "Active" if a["active"] else "Disabled",
        "Locked until": a["locked_until"] if _is_locked(a) else "",
        "Failed sign-ins": a["failed_logins"],
        "Must change password": "Yes" if a["must_change_password"] else "",
    } for a in accounts]), hide_index=True, width="stretch")


def _run(action, *args, done):
    """Call a service; show its outcome. `done` is the success message."""
    try:
        changed = action(*args)
    except services.ServiceError as e:
        st.error(str(e))
        return
    if changed is False:
        st.info("Nothing to change.")
        return
    st.session_state["admin_flash"] = done
    st.rerun()


def _manage_account(user, accounts):
    st.markdown("##### Manage an account")
    if flash := st.session_state.pop("admin_flash", None):
        st.success(flash)
    if not accounts:
        st.caption("No other accounts yet. You can't change your own account here.")
        return
    by_name = {a["username"]: a for a in accounts}
    name = st.selectbox("Account", list(by_name), key="acct_pick",
                        help="Your own account isn't listed: another admin must change it.")
    a = by_name[name]
    admin = user["username"]

    with st.form(f"acct_form_{name}", clear_on_submit=True):
        action = st.radio("Action", [
            "Reset password", "Unlock", "Disable" if a["active"] else "Enable", "Change role"],
            horizontal=True, key=f"acct_action_{name}")
        role = st.selectbox("New role (for Change role)", LOGIN_ROLES,
                            index=LOGIN_ROLES.index(a["role"]), format_func=ROLE_LABELS.get,
                            key=f"acct_role_{name}")
        temp = st.text_input(f"Temporary password (for Reset password; at least "
                             f"{MIN_PASSWORD_LENGTH} characters)", type="password",
                             key=f"acct_temp_{name}")
        reason = st.text_input("Reason *", key=f"acct_reason_{name}",
                               help="Required — recorded in the audit trail.")
        submitted = st.form_submit_button("Apply", type="primary")
    if not submitted:
        if _is_locked(a):
            st.warning(f"{name} is locked until {a['locked_until']} (UTC).")
        return
    if action == "Reset password":
        _run(services.reset_password, name, temp, admin, reason,
             done=f"Temporary password set for {name}. Give it to them securely; "
                  "they must change it at their next sign-in.")
    elif action == "Unlock":
        _run(services.unlock_user, name, admin, reason, done=f"{name} is unlocked.")
    elif action in ("Disable", "Enable"):
        _run(services.set_user_active, name, action == "Enable", admin, reason,
             done=f"{name} is {'enabled' if action == 'Enable' else 'disabled'}.")
    else:
        _run(services.change_role, name, role, admin, reason,
             done=f"{name} is now {ROLE_LABELS[role]}.")


def _create_account(user):
    with st.expander("➕ Create an account"):
        with st.form("acct_create", clear_on_submit=True):
            username = st.text_input("Username *", key="new_username")
            role = st.selectbox("Role", LOGIN_ROLES, format_func=ROLE_LABELS.get,
                                index=LOGIN_ROLES.index(ROLE_LAB_TECH), key="new_role")
            temp = st.text_input(f"Temporary password * (at least {MIN_PASSWORD_LENGTH} "
                                 "characters)", type="password", key="new_temp")
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            _run(services.create_user, username.strip(), role, temp, user["username"],
                 done=f"Created {username.strip()}. They must change the temporary "
                      "password at first sign-in.")


if __name__ == "__main__":     # run as a page by st.navigation (views/navigation.py)
    show()
