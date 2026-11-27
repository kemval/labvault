"""
repo/users.py — accounts and authentication.
"""

import hashlib

from config import ConfigError
from repo.core import get_conn


def hash_pw(password: str) -> str:
    """SHA-256 hash a password. Simple, fast, and one-way — passwords never stored raw."""
    return hashlib.sha256(password.encode()).hexdigest()


DEMO_USERS = [
    # (username, password, role)
    ("admin",  "admin123", "admin"),
    ("kembly", "lab2024",  "lab_tech"),
    ("carlos", "lab2024",  "lab_tech"),
    ("maria",  "lab2024",  "lab_tech"),
]


MIN_ADMIN_PASSWORD_LENGTH = 12


def seed_users(demo: bool, admin_password=None):
    """
    Create the initial accounts — only when the users table is empty, so
    accounts that were deleted or changed later are never silently re-created.

    Demo mode seeds DEMO_USERS. Secure mode seeds a single `admin` with the
    operator-supplied password, and refuses to run on a database that still
    contains accounts with published demo passwords.
    Raises ConfigError when the app must not start.
    """
    conn = get_conn()
    try:
        has_users = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

        if not demo:
            exposed = [
                username for username, password, _ in DEMO_USERS
                if conn.execute(
                    "SELECT 1 FROM users WHERE username = ? AND password = ?",
                    (username, hash_pw(password)),
                ).fetchone()
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
            rows = [(u, hash_pw(p), r) for u, p, r in DEMO_USERS]
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
            rows = [("admin", hash_pw(admin_password), "admin")]

        conn.executemany(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()


def authenticate(username: str, password: str):
    """
    Look up a user by username + hashed password.
    Returns the full user row as a dict, or None if credentials don't match.
    We hash the input before querying so the DB never sees a plaintext password.
    """
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("""
        SELECT * FROM users WHERE username = ? AND password = ?
    """, (username, hash_pw(password))).fetchone()
    conn.close()
    return dict(row) if row else None


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
        "SELECT username FROM users WHERE role = 'lab_tech'"
    ).fetchall()
    conn.close()
    return [r["username"] for r in rows]
