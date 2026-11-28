"""Password storage, lockout and idle timeout (audit H6, migration 6, ADR 0013)."""
import hashlib
import sqlite3
import time

import pytest

import services
from domain import LOCKOUT_MINUTES, MAX_FAILED_LOGINS
from repo import core, passwords, schema
from test_app_login import login, run_app
from test_services import audit, rows


def stored(username):
    return rows("SELECT * FROM users WHERE username = ?", (username,))[0]


def set_user(username, **cols):
    with core.transaction() as conn:
        for col, value in cols.items():
            conn.execute(f"UPDATE users SET {col} = ? WHERE username = ?", (value, username))


# ── hashing ──────────────────────────────────────────────────

def test_hashes_are_salted_and_verify():
    a, b = passwords.hash_password("lab2024"), passwords.hash_password("lab2024")
    assert a != b and a.startswith("scrypt$")
    assert passwords.verify("lab2024", a) and not passwords.verify("lab2025", a)


@pytest.mark.parametrize("bad", ["!", "", "scrypt$x", "md5$1$1$1$00$00", None])
def test_unparseable_hashes_never_match(bad):
    assert passwords.verify("!", bad) is False


def test_cost_change_triggers_rehash(monkeypatch):
    h = passwords.hash_password("pw")
    assert not passwords.needs_rehash(h)
    monkeypatch.setattr(passwords, "COST", {"n": 2 ** 5, "r": 1, "p": 1})
    assert passwords.needs_rehash(h) and passwords.verify("pw", h)


def test_migration_6_wraps_legacy_sha256_hashes():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (username TEXT, password TEXT, role TEXT)")
    legacy = hashlib.sha256(b"lab2024").hexdigest()
    conn.executemany("INSERT INTO users VALUES (?, ?, ?)",
                     [("kembly", legacy, "lab_tech"), ("system", "!", "system")])
    schema._m006_password_security(conn)
    (kembly, k_fail, k_lock), (system, *_) = conn.execute(
        "SELECT password, failed_logins, locked_until FROM users ORDER BY username")
    assert legacy not in kembly and kembly.startswith("scrypt-sha256$")
    assert passwords.verify("lab2024", kembly) and (k_fail, k_lock) == (0, None)
    assert system == "!"                       # unusable password left alone


# ── sign-in ──────────────────────────────────────────────────

def test_success_returns_user_without_hash(lab_db):
    user = services.sign_in("kembly", "lab2024")
    assert user["username"] == "kembly" and "password" not in user


def test_legacy_hash_is_upgraded_at_next_sign_in(lab_db):
    set_user("kembly", password=passwords.wrap_legacy(hashlib.sha256(b"lab2024").hexdigest()))
    assert services.sign_in("kembly", "lab2024")
    assert stored("kembly")["password"].startswith("scrypt$")
    assert services.sign_in("kembly", "lab2024")           # still works after upgrade


def test_repeated_failures_lock_the_account(lab_db):
    for _ in range(MAX_FAILED_LOGINS - 1):
        assert services.sign_in("kembly", "wrong") is None
    assert stored("kembly")["failed_logins"] == MAX_FAILED_LOGINS - 1
    assert services.sign_in("kembly", "wrong") is None
    [locked] = audit("ACCOUNT_LOCKED")
    assert locked["user"] == "kembly" and stored("kembly")["locked_until"] > core.utc_now()
    # Even the right password is refused while locked.
    assert services.sign_in("kembly", "lab2024") is None
    assert "Account locked" in audit("LOGIN_FAILED")[-1]["detail"]


def test_lock_expires(lab_db):
    set_user("kembly", locked_until=core.utc_after(minutes=-1))
    assert services.sign_in("kembly", "lab2024")
    assert (stored("kembly")["failed_logins"], stored("kembly")["locked_until"]) == (0, None)


def test_lock_lasts_the_configured_time(lab_db):
    for _ in range(MAX_FAILED_LOGINS):
        services.sign_in("kembly", "wrong")
    assert core.utc_after(LOCKOUT_MINUTES - 1) < stored("kembly")["locked_until"] \
        <= core.utc_after(LOCKOUT_MINUTES)


def test_success_resets_the_failure_count(lab_db):
    services.sign_in("kembly", "wrong")
    services.sign_in("kembly", "lab2024")
    assert stored("kembly")["failed_logins"] == 0


def test_unknown_user_changes_no_account(lab_db):
    before = rows("SELECT * FROM users")
    assert services.sign_in("nobody", "x") is None
    assert rows("SELECT * FROM users") == before
    assert audit("LOGIN_FAILED")[-1]["user"] == "system"


# ── the app ──────────────────────────────────────────────────

def errors(at):
    return [e.value for e in at.error]


def test_locked_and_unknown_accounts_get_the_same_message(lab_db, settings):
    settings(demo="true")
    set_user("kembly", locked_until=core.utc_after(minutes=10))
    locked = errors(login(run_app(), "kembly", "lab2024"))
    unknown = errors(login(run_app(), "nobody", "lab2024"))
    assert locked == unknown and "locked for" in locked[0]


def test_idle_session_is_signed_out(lab_db, settings):
    settings(demo="true")
    at = login(run_app(), "kembly", "lab2024")
    assert at.session_state.logged_in
    at.session_state.last_activity = time.time() - 31 * 60
    at.run()
    assert not at.session_state.logged_in
    assert any("signed out after 30 minutes" in i.value for i in at.info)
    assert audit("SESSION_TIMEOUT")[0]["user"] == "kembly"


def test_active_session_stays_signed_in(lab_db, settings):
    settings(demo="true")
    at = login(run_app(), "kembly", "lab2024")
    at.session_state.last_activity = time.time() - 29 * 60
    at.run()
    assert at.session_state.logged_in and audit("SESSION_TIMEOUT") == []
