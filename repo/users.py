"""
repo/users.py — accounts and authentication.
"""

from config import ConfigError
from domain import ROLE_ADMIN, ROLE_LAB_TECH, ROLE_SYSTEM
from repo import passwords
from repo.core import get_conn


DEMO_USERS = [
    # (username, password, role)
    ("admin",  "admin123", ROLE_ADMIN),
    ("kembly", "lab2024",  ROLE_LAB_TECH),
    ("carlos", "lab2024",  ROLE_LAB_TECH),
    ("maria",  "lab2024",  ROLE_LAB_TECH),
]


MIN_ADMIN_PASSWORD_LENGTH = 12


def seed_users(demo: bool, admin_password=None):
    """
    Create the initial accounts — only when no login accounts exist, so
    accounts that were deleted or changed later are never silently re-created.

    Demo mode seeds DEMO_USERS. Secure mode seeds a single `admin` with the
    operator-supplied password, and refuses to run on a database that still
    contains accounts with published demo passwords.
    Raises ConfigError when the app must not start.
    """
    conn = get_conn()
    try:
        # The non-login system accounts (migration 3) don't count as set up.
        has_users = conn.execute(
            "SELECT 1 FROM users WHERE role != ? LIMIT 1", (ROLE_SYSTEM,)).fetchone() is not None

        if not demo:
            stored = dict(conn.execute("SELECT username, password FROM users").fetchall())
            exposed = [
                username for username, password, _ in DEMO_USERS
                if username in stored and passwords.verify(password, stored[username])
            ]
            if exposed:
                raise ConfigError(
                    "These accounts still use the published demo passwords: "
                    f"{', '.join(exposed)}. Use a fresh database for a non-demo "
                    "deployment, or set LABVAULT_DEMO_MODE=true for a demo."
                )

        if has_users:
            return

        if demo:
            rows = [(u, passwords.hash_password(p), r) for u, p, r in DEMO_USERS]
        else:
            if not admin_password:
                raise ConfigError(
                    "No users exist yet. Set LABVAULT_ADMIN_PASSWORD to create the "
                    "initial admin account, or set LABVAULT_DEMO_MODE=true for a demo."
                )
            if len(admin_password) < MIN_ADMIN_PASSWORD_LENGTH:
                raise ConfigError(
                    f"LABVAULT_ADMIN_PASSWORD must be at least "
                    f"{MIN_ADMIN_PASSWORD_LENGTH} characters."
                )
            rows = [("admin", passwords.hash_password(admin_password), ROLE_ADMIN)]

        conn.executemany(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()


def login_account(conn, username: str):
    """The login account (never a system account) with its stored hash and
    lockout state, or None. For services.sign_in, inside its transaction."""
    row = conn.execute("SELECT * FROM users WHERE username = ? AND role != ?",
                       (username, ROLE_SYSTEM)).fetchone()
    return dict(row) if row else None


def record_failure(conn, username: str, failed_logins: int, locked_until):
    conn.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE username = ?",
                 (failed_logins, locked_until, username))


def record_success(conn, username: str, new_hash=None):
    """Clear the failure count; store an upgraded hash when given one."""
    conn.execute("UPDATE users SET failed_logins = 0, locked_until = NULL, "
                 "password = COALESCE(?, password) WHERE username = ?", (new_hash, username))


def authenticate(username: str, password: str):
    """
    The user (without password hash) if the credentials match, else None.
    No lockout or audit — app code signs in through services.sign_in.
    System accounts (imports, simulator, migrations) can never log in.
    """
    conn = get_conn()
    try:
        account = login_account(conn, username)
    finally:
        conn.close()
    if account is None or not passwords.verify(password, account["password"]):
        return None
    return public(account)


def public(account: dict) -> dict:
    """The account without its password hash, for the session."""
    return {k: v for k, v in account.items() if k != "password"}


def all_users():
    """Fetch all users — just username and role, no password hashes leaving the DB."""
    conn = get_conn()
    rows = conn.execute("SELECT username, role FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def lab_techs():
    """
    Return a list of lab tech usernames — used to populate assignment dropdowns.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT username FROM users WHERE role = ?", (ROLE_LAB_TECH,)
    ).fetchall()
    conn.close()
    return [r["username"] for r in rows]
