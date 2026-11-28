"""Account management: create, disable, roles, resets, unlock (roadmap 3.6, ADR 0017)."""
import pytest

import services
from repo import core, users
from test_app_login import go, registered_pages, login, no_network, run_app  # noqa: F401
from test_services import BASE, audit, rows

TEMP = "temporary-pass-1"
NEW = "my-own-password-9"


def account(username):
    return rows("SELECT * FROM users WHERE username = ?", (username,))[0]


def lock(username):
    with core.transaction() as conn:
        conn.execute("UPDATE users SET failed_logins = 3, locked_until = ? WHERE username = ?",
                     (core.utc_after(minutes=10), username))


# ── creating accounts ───────────────────────────────────────

def test_admin_creates_account_that_must_change_its_password(lab_db):
    services.create_user("nina", "lab_tech", TEMP, "admin")
    a = account("nina")
    assert (a["role"], a["active"], a["must_change_password"]) == ("lab_tech", 1, 1)
    assert TEMP not in a["password"]
    [row] = audit("USER_CREATED")
    assert (row["user"], row["target_id"], row["new_value"]) == ("admin", "nina", "lab_tech")
    assert services.sign_in("nina", TEMP)["must_change_password"] == 1


@pytest.mark.parametrize("username, role, password, message", [
    ("kembly", "lab_tech", TEMP, "already taken"),
    ("system", "lab_tech", TEMP, "already taken"),
    ("Nina", "lab_tech", TEMP, "lowercase"),
    ("ab", "lab_tech", TEMP, "3–32"),
    ("nina", "system", TEMP, "Unknown role"),
    ("nina", "lab_tech", "short", "at least 12"),
    ("nina.lab.tech", "lab_tech", "NINA.LAB.TECH", "can't be the username"),
])
def test_invalid_accounts_are_refused(lab_db, username, role, password, message):
    with pytest.raises(services.ServiceError, match=message):
        services.create_user(username, role, password, "admin")
    assert audit("USER_CREATED") == []


def test_only_admins_manage_accounts(lab_db):
    with pytest.raises(services.PermissionDeniedError, match="Only an admin"):
        services.create_user("nina", "lab_tech", TEMP, "kembly")
    with pytest.raises(services.PermissionDeniedError, match="Only an admin"):
        services.unlock_user("carlos", "kembly", "help")


def test_admin_cannot_change_own_account_or_system_accounts(lab_db):
    with pytest.raises(services.PermissionDeniedError, match="your own account"):
        services.set_user_active("admin", False, "admin", "leaving")
    with pytest.raises(services.PermissionDeniedError, match="your own account"):
        services.change_role("admin", "lab_tech", "admin", "test")
    with pytest.raises(services.PermissionDeniedError, match="doesn't exist"):
        services.reset_password("system", TEMP, "admin", "test")


def test_admin_actions_need_a_reason(lab_db):
    for call in (lambda: services.set_user_active("maria", False, "admin", " "),
                 lambda: services.change_role("maria", "admin", "admin", ""),
                 lambda: services.reset_password("maria", TEMP, "admin", ""),
                 lambda: services.unlock_user("maria", "admin", "")):
        with pytest.raises(services.ServiceError, match="reason"):
            call()


# ── changing your own password ──────────────────────────────

def test_change_password_clears_the_flag(lab_db):
    services.create_user("nina", "lab_tech", TEMP, "admin")
    services.change_password("nina", TEMP, NEW)
    assert account("nina")["must_change_password"] == 0
    assert services.sign_in("nina", TEMP) is None and services.sign_in("nina", NEW)
    assert audit("PASSWORD_CHANGED")[0]["user"] == "nina"


def test_wrong_current_password_counts_toward_lockout(lab_db):
    with pytest.raises(services.SignatureError):
        services.change_password("kembly", "wrong", NEW)
    assert account("kembly")["failed_logins"] == 1
    assert audit("PASSWORD_CHANGE_FAILED")[0]["user"] == "kembly"
    assert services.sign_in("kembly", "lab2024")              # unchanged


def test_new_password_must_differ_and_follow_the_rules(lab_db):
    with pytest.raises(services.ServiceError, match="at least 12"):
        services.change_password("kembly", "lab2024", "short")
    services.change_password("kembly", "lab2024", NEW)
    with pytest.raises(services.ServiceError, match="different"):
        services.change_password("kembly", NEW, NEW)


# ── disabling ───────────────────────────────────────────────

def test_disable_is_blocked_while_samples_are_open(lab_db):
    sid = services.register_sample(BASE, "admin")              # assigned to kembly
    with pytest.raises(services.ServiceError, match=f"1 open sample.*{sid}.*Reassign"):
        services.set_user_active("kembly", False, "admin", "left the company")
    assert account("kembly")["active"] == 1

    services.update_sample(sid, 1, "admin", assigned_to="carlos", reason="handover")
    assert services.set_user_active("kembly", False, "admin", "left the company")
    [row] = audit("USER_DISABLED")
    assert (row["old_value"], row["new_value"], row["reason"]) == \
        ("Active", "Disabled", "left the company")


def test_disabled_account_cannot_sign_in_or_change_data(lab_db):
    services.set_user_active("maria", False, "admin", "on leave")
    assert services.sign_in("maria", "lab2024") is None
    assert audit("LOGIN_FAILED")[0]["detail"] == "Account disabled"
    with pytest.raises(services.PermissionDeniedError):
        services.register_sample(BASE, "maria")
    assert "maria" not in users.lab_techs()

    assert services.set_user_active("maria", True, "admin", "back")
    assert services.sign_in("maria", "lab2024") and "maria" in users.lab_techs()
    assert services.set_user_active("maria", True, "admin", "again") is False


# ── roles, resets, unlocks ──────────────────────────────────

def test_role_change_is_audited_and_blocked_by_open_samples(lab_db):
    sid = services.register_sample(BASE, "admin")
    with pytest.raises(services.ServiceError, match="open sample"):
        services.change_role("kembly", "admin", "admin", "promotion")
    services.update_sample(sid, 1, "admin", status="Rejected", reason="damaged")
    assert services.change_role("kembly", "admin", "admin", "promotion")
    [row] = audit("USER_ROLE_CHANGED")
    assert (row["old_value"], row["new_value"]) == ("lab_tech", "admin")
    assert services.change_role("kembly", "admin", "admin", "again") is False


def test_reset_sets_a_temporary_password_and_clears_the_lock(lab_db):
    lock("carlos")
    services.reset_password("carlos", TEMP, "admin", "forgot password")
    a = account("carlos")
    assert (a["must_change_password"], a["failed_logins"], a["locked_until"]) == (1, 0, None)
    assert services.sign_in("carlos", "lab2024") is None
    assert services.sign_in("carlos", TEMP)
    assert TEMP not in str(audit("PASSWORD_RESET"))


def test_unlock_ends_a_lockout(lab_db):
    assert services.unlock_user("carlos", "admin", "verified by phone") is False
    lock("carlos")
    assert services.sign_in("carlos", "lab2024") is None       # locked
    assert services.unlock_user("carlos", "admin", "verified by phone")
    assert services.sign_in("carlos", "lab2024")
    assert audit("ACCOUNT_UNLOCKED")[0]["reason"] == "verified by phone"


# ── the app ─────────────────────────────────────────────────

def test_temporary_password_must_be_changed_before_anything_else(lab_db, settings):
    settings(demo="true")
    services.create_user("nina", "lab_tech", TEMP, "admin")
    at = login(run_app(), "nina", TEMP)
    assert "Dashboard" not in registered_pages(at)              # no navigation yet
    assert any("temporary password" in i.value for i in at.info)

    at.text_input(key="pw_current").input(TEMP)
    at.text_input(key="pw_new").input(NEW)
    at.text_input(key="pw_confirm").input(NEW)
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert "Dashboard" in registered_pages(at)
    assert account("nina")["must_change_password"] == 0


def test_mismatched_new_passwords_change_nothing(lab_db, settings):
    settings(demo="true")
    at = login(run_app(), "kembly", "lab2024")
    go(at, "My Account")
    at.text_input(key="pw_current").input("lab2024")
    at.text_input(key="pw_new").input(NEW)
    at.text_input(key="pw_confirm").input(NEW + "x")
    next(b for b in at.button if b.label == "Change password").click().run()
    assert any("don't match" in e.value for e in at.error)
    assert audit("PASSWORD_CHANGED") == []


def test_disabling_ends_the_users_session(lab_db, settings):
    settings(demo="true")
    at = login(run_app(), "maria", "lab2024")
    services.set_user_active("maria", False, "admin", "on leave")
    at.run()
    assert not at.session_state.logged_in
    assert any("account was disabled" in w.value for w in at.warning)
    assert audit("LOGOUT")[0]["detail"] == "Signed out: account disabled"


def test_role_change_applies_at_the_next_click(lab_db, settings):
    settings(demo="true")
    at = login(run_app(), "maria", "lab2024")
    assert "Admin" not in registered_pages(at)
    services.change_role("maria", "admin", "admin", "new QA lead")
    at.run()
    assert "Admin" in registered_pages(at)


def admin_page():
    at = login(run_app(), "admin", "admin123")
    go(at, "Admin")
    assert not at.exception, at.exception
    return at


def test_admin_page_unlocks_an_account(lab_db, settings):
    settings(demo="true")
    lock("carlos")
    at = admin_page()
    assert "admin" not in at.selectbox(key="acct_pick").options       # never your own
    at.selectbox(key="acct_pick").set_value("carlos").run()
    assert any("locked until" in w.value for w in at.warning)
    at.radio(key="acct_action_carlos").set_value("Unlock")
    at.text_input(key="acct_reason_carlos").input("verified by phone")
    next(b for b in at.button if b.label == "Apply").click().run()
    assert not at.exception, at.exception
    assert any("carlos is unlocked" in s.value for s in at.success)
    assert account("carlos")["locked_until"] is None


def test_admin_page_shows_why_disable_is_refused(lab_db, settings):
    settings(demo="true")
    sid = services.register_sample(BASE, "admin")
    at = admin_page()
    at.selectbox(key="acct_pick").set_value("kembly").run()
    at.radio(key="acct_action_kembly").set_value("Disable")
    at.text_input(key="acct_reason_kembly").input("left")
    next(b for b in at.button if b.label == "Apply").click().run()
    assert any(sid in e.value for e in at.error)
    assert account("kembly")["active"] == 1


def test_admin_page_creates_an_account(lab_db, settings):
    settings(demo="true")
    at = admin_page()
    at.text_input(key="new_username").input("nina")
    at.text_input(key="new_temp").input(TEMP)
    next(b for b in at.button if b.label == "Create account").click().run()
    assert not at.exception, at.exception
    assert any("Created nina" in s.value for s in at.success)
    assert account("nina")["must_change_password"] == 1


def test_samples_cannot_be_assigned_to_a_disabled_account(lab_db):
    services.set_user_active("maria", False, "admin", "on leave")
    with pytest.raises(services.ServiceError, match="active lab techs; maria"):
        services.register_sample({**BASE, "assigned_to": "maria"}, "admin")
    sid = services.register_sample({**BASE, "assigned_to": None}, "admin")
    with pytest.raises(services.PermissionDeniedError, match="active lab techs; maria"):
        services.update_sample(sid, 1, "admin", assigned_to="maria", reason="workload")
