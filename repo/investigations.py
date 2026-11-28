"""
repo/investigations.py — OOS investigations (migration 8, ADR 0015).
Triggers keep them: never deleted, final once closed, and not closed by
the result's own analyst.
"""

from domain import RESULT_OOS, STATUS_IN_PROGRESS
from repo.core import get_conn, utc_now

_SELECT = """
    SELECT i.*, r.sample_id, r.test_name, r.result_value, r.result_unit, r.spec_min,
           r.spec_max, r.tested_by, r.tested_at, r.is_simulated,
           s.product_name, s.status AS sample_status
    FROM oos_investigations i
    JOIN test_results r ON r.id = i.result_id
    JOIN samples s ON s.sample_id = r.sample_id"""


def open_investigation(conn, result_id: int, user: str) -> int:
    return conn.execute("INSERT INTO oos_investigations (result_id, opened_by, opened_at) "
                        "VALUES (?, ?, ?)", (result_id, user, utc_now())).lastrowid


def open_for_samples(conn, sample_ids, user: str) -> int:
    """Open an investigation for each OOS result without one on these
    samples while In Progress (the bulk FDA import); returns how many."""
    ids = list(sample_ids)
    if not ids:
        return 0
    marks = ", ".join("?" * len(ids))
    return conn.execute(f"""
        INSERT INTO oos_investigations (result_id, opened_by, opened_at)
        SELECT r.id, ?, ? FROM test_results r
        JOIN samples s ON s.sample_id = r.sample_id
        LEFT JOIN oos_investigations i ON i.result_id = r.id
        WHERE r.status = ? AND s.status = ? AND i.id IS NULL AND r.sample_id IN ({marks})
        ORDER BY r.id""", [user, utc_now(), RESULT_OOS, STATUS_IN_PROGRESS, *ids]).rowcount


def find_investigation(conn, investigation_id: int):
    row = conn.execute(f"{_SELECT} WHERE i.id = ?", (investigation_id,)).fetchone()
    return dict(row) if row else None


def close_investigation(conn, investigation_id: int, user: str, conclusion: str,
                        findings: str) -> str:
    """Close an open investigation; returns the UTC time closed."""
    closed_at = utc_now()
    conn.execute("""
        UPDATE oos_investigations
        SET status = 'Closed', conclusion = ?, findings = ?, closed_by = ?, closed_at = ?
        WHERE id = ? AND status = 'Open'""",
                 (conclusion, findings, user, closed_at, investigation_id))
    return closed_at


def all_investigations():
    """Open ones first (oldest first), then closed ones (newest first)."""
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute(
            f"{_SELECT} ORDER BY i.status = 'Closed', "
            "CASE WHEN i.status = 'Open' THEN i.id ELSE -i.id END")]
    finally:
        conn.close()
