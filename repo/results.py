"""
repo/results.py — test result rows.
"""

from domain import (CONCLUSION_CONFIRMED, CONCLUSION_LAB_ERROR, INVESTIGATION_OPEN,
                    OOS_CATEGORIES, OOS_CONFIRMED, OOS_COUNTED, OOS_INVALIDATED,
                    OOS_NOT_INVESTIGATED, OOS_UNDER_INVESTIGATION, RESULT_OOS, REVIEW_REJECTED)
from repo.core import get_conn, run_in


def insert_test_result(data: dict, conn=None) -> int:
    """
    Insert a test result row; returns its id. No IGNORE — a sample can be
    re-tested. Pass `conn` to join the caller's transaction. App code should
    use services.record_result, which also writes the audit row.
    """
    def run(c):
        return c.execute("""
            INSERT INTO test_results
                (sample_id, test_name, result_value, result_unit,
                 spec_min, spec_max, status, tested_by, tested_at, notes,
                 spec_id, spec_version)
            VALUES
                (:sample_id, :test_name, :result_value, :result_unit,
                 :spec_min, :spec_max, :status, :tested_by, :tested_at, :notes,
                 :spec_id, :spec_version)
        """, {"spec_id": None, "spec_version": None, **data}).lastrowid

    return run_in(conn, run)


# Each result's signature (migration 7): meaning, signer, time and reason.
# and its OOS investigation, if any (migration 8).
REVIEW_COLUMNS = ("g.meaning AS review, g.signed_by AS reviewed_by, "
                  "g.signed_at AS reviewed_at, g.reason AS review_reason, "
                  "i.id AS investigation_id, i.status AS investigation_status, "
                  "i.conclusion AS conclusion")
REVIEW_JOIN = ("LEFT JOIN result_signatures g ON g.result_id = r.id "
               "LEFT JOIN oos_investigations i ON i.result_id = r.id")


def results_for_sample(sample_id: str):
    """Fetch all test results for a specific sample, newest first."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT r.*, {REVIEW_COLUMNS} FROM test_results r {REVIEW_JOIN}
        WHERE r.sample_id = ? ORDER BY r.id DESC
    """.format(REVIEW_COLUMNS=REVIEW_COLUMNS, REVIEW_JOIN=REVIEW_JOIN), (sample_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def all_results():
    """
    Fetch every test result in the system — used by Reports.
    Potentially a big query, but Reports is an explicit user action,
    not a background poll, so the load is acceptable.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT r.*, {REVIEW_COLUMNS} FROM test_results r {REVIEW_JOIN}
        ORDER BY r.id DESC
    """.format(REVIEW_COLUMNS=REVIEW_COLUMNS, REVIEW_JOIN=REVIEW_JOIN)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# domain.oos_category in SQL, over test_results r {REVIEW_JOIN} (ADR 0019).
OOS_CATEGORY_SQL = f"""
    CASE WHEN r.status != '{RESULT_OOS}' THEN NULL
         WHEN i.conclusion = '{CONCLUSION_LAB_ERROR}' OR g.meaning = '{REVIEW_REJECTED}'
              THEN '{OOS_INVALIDATED}'
         WHEN i.conclusion = '{CONCLUSION_CONFIRMED}' THEN '{OOS_CONFIRMED}'
         WHEN i.status = '{INVESTIGATION_OPEN}' THEN '{OOS_UNDER_INVESTIGATION}'
         ELSE '{OOS_NOT_INVESTIGATED}' END"""


def oos_results(limit: int = 10):
    """
    The most recent OOS results that still count (not invalidated), with
    where each stands — for the dashboard alerts.
    """
    marks = ", ".join("?" * len(OOS_COUNTED))
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT * FROM (
            SELECT r.id, r.sample_id, r.test_name, r.result_value, r.result_unit,
                   r.spec_min, r.spec_max, r.tested_by, r.tested_at, r.is_simulated,
                   {OOS_CATEGORY_SQL} AS oos_category
            FROM test_results r {REVIEW_JOIN}
            WHERE r.status = ?)
        WHERE oos_category IN ({marks})
        ORDER BY id DESC LIMIT ?
    """, (RESULT_OOS, *OOS_COUNTED, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def oos_breakdown():
    """
    {category: count} for every OOS category (zeros included), plus
    "counted": the headline OOS total, which leaves out invalidated results.
    """
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT {OOS_CATEGORY_SQL} AS category, COUNT(*) AS n
        FROM test_results r {REVIEW_JOIN} WHERE r.status = ? GROUP BY category
    """, (RESULT_OOS,)).fetchall()
    conn.close()
    counts = {c: 0 for c in OOS_CATEGORIES}
    counts.update({r["category"]: r["n"] for r in rows})
    counts["counted"] = sum(counts[c] for c in OOS_COUNTED)
    return counts
