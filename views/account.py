"""
views/account.py — the signed-in user's own account: change password (ADR 0017).
Also shown on its own, before anything else, when a password set by an
admin must be changed.
"""

import streamlit as st

import services
from domain import MIN_PASSWORD_LENGTH
from views.ui import page_header


def password_form(user, forced=False):
    with st.form("change_password"):
        current = st.text_input("Temporary password" if forced else "Current password",
                                type="password", key="pw_current")
        new = st.text_input(f"New password (at least {MIN_PASSWORD_LENGTH} characters)",
                            type="password", key="pw_new")
        confirm = st.text_input("Repeat new password", type="password", key="pw_confirm")
        submitted = st.form_submit_button("Change password", type="primary")
    if not submitted:
        return
    if new != confirm:
        st.error("The new passwords don't match.")
        return
    try:
        services.change_password(user["username"], current, new)
    except services.ServiceError as e:
        st.error(str(e))
        return
    st.session_state.user = {**user, "must_change_password": 0}
    if forced:
        st.rerun()
    st.success("Password changed.")


def show():
    page_header("🔑 My Account", "Change your password")
    user = st.session_state.user
    st.markdown(f"Signed in as **{user['username']}** ({user['role'].replace('_', ' ')}).")
    password_form(user)
