"""
repo/audit.py — audit trail rows.
"""

from datetime import datetime

from repo.core import get_conn


def write_audit(conn, user: str, action: str, module: str,
                target_id: str = "", detail: str = ""):
    """
    Insert one audit row on `conn` without committing, so it lands in the
    same transaction as the change it describes. services.py uses this for
    every data change; the caller clears caches after commit.
    """
    conn.execute("""
        INSERT INTO audit_trail (timestamp, user, action, module, target_id, detail)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action, module, target_id, detail))


def recent_audit(limit: int = 200):
    """
    Fetch the most recent audit entries, newest first.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM audit_trail ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
