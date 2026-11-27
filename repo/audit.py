"""
repo/audit.py — the audit trail. Append-only: migration 4 adds triggers
that reject UPDATE and DELETE (ADR 0008).
"""

from repo.core import get_conn, utc_now

# Sign-in events: kept in the trail, but not "activity" on the dashboard.
SESSION_ACTIONS = ("LOGIN", "LOGIN_FAILED", "LOGOUT")


def write_audit(conn, user: str, action: str, module: str, target_id: str = "",
                detail: str = "", old_value=None, new_value=None, reason=None):
    """
    Insert one audit row on `conn` without committing, so it lands in the
    same transaction as the change it describes. For a change to a field,
    pass its old and new value and the user's reason. The caller clears
    caches after commit.
    """
    conn.execute("""
        INSERT INTO audit_trail
            (timestamp, user, action, module, target_id, detail, old_value, new_value, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (utc_now(), user, action, module, target_id, detail,
          None if old_value is None else str(old_value),
          None if new_value is None else str(new_value), reason))


def recent_audit(limit: int = 200, exclude_actions=()):
    """The most recent audit entries, newest first."""
    marks = ", ".join("?" * len(exclude_actions))
    where = f"WHERE action NOT IN ({marks})" if exclude_actions else ""
    conn = get_conn()
    try:
        rows = conn.execute(f"SELECT * FROM audit_trail {where} ORDER BY id DESC LIMIT ?",
                            (*exclude_actions, limit)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def search_audit(user: str = "", action: str = "", limit: int = 100, offset: int = 0):
    """
    One page of the audit trail, newest first, filtered in SQL so every entry
    is reachable. `user` is a case-insensitive substring; `action` exact.
    Returns (rows, total matching).
    """
    clauses, params = [], []
    if user:
        clauses.append("instr(lower(user), lower(?)) > 0")  # no LIKE wildcards to escape
        params.append(user)
    if action:
        clauses.append("action = ?")
        params.append(action)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_conn()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM audit_trail {where}", params).fetchone()[0]
        rows = conn.execute(f"SELECT * FROM audit_trail {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                            (*params, limit, offset)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows], total


def audit_actions():
    """Every action type present in the trail, for the filter dropdown."""
    conn = get_conn()
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT action FROM audit_trail ORDER BY action")]
    finally:
        conn.close()
