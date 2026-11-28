"""
repo/signatures.py — e-signatures on test results (migration 7, ADR 0014).
Append-only: triggers reject UPDATE and DELETE, and a signature by the
result's own analyst.
"""

from domain import STATUS_IN_PROGRESS
from repo.core import get_conn, utc_now


def insert_signature(conn, result_id: int, user: str, meaning: str, reason) -> str:
    """Sign a result inside the caller's transaction; returns the UTC time signed."""
    signed_at = utc_now()
    conn.execute("""
        INSERT INTO result_signatures (result_id, signed_by, meaning, reason, signed_at)
        VALUES (?, ?, ?, ?, ?)""", (result_id, user, meaning, reason, signed_at))
    return signed_at


def result_for_review(conn, result_id: int):
    """The result with what review_error needs (sample status, signature), or None."""
    row = conn.execute("""
        SELECT r.*, s.status AS sample_status, g.meaning AS review
        FROM test_results r
        JOIN samples s ON s.sample_id = r.sample_id
        LEFT JOIN result_signatures g ON g.result_id = r.id
        WHERE r.id = ?""", (result_id,)).fetchone()
    return dict(row) if row else None


def awaiting_review():
    """Unsigned results on In Progress samples, oldest first, for the review queue."""
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute("""
            SELECT r.*, s.product_name, s.sample_type, s.status AS sample_status,
                   NULL AS review
            FROM test_results r
            JOIN samples s ON s.sample_id = r.sample_id
            LEFT JOIN result_signatures g ON g.result_id = r.id
            WHERE g.id IS NULL AND s.status = ?
            ORDER BY r.id""", (STATUS_IN_PROGRESS,))]
    finally:
        conn.close()
