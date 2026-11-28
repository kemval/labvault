"""
repo/results.py — test result rows.
"""

from domain import RESULT_OOS
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


def results_for_sample(sample_id: str):
    """Fetch all test results for a specific sample, newest first."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM test_results WHERE sample_id = ? ORDER BY id DESC
    """, (sample_id,)).fetchall()
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
        SELECT * FROM test_results ORDER BY id DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def oos_results(limit: int = 10):
    """
    Fetch only the Out-of-Spec results — cheaper than loading everything and
    filtering in Python. The index on test_results.status makes this fast.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT sample_id, test_name, result_value, result_unit,
               spec_min, spec_max, tested_by, tested_at, is_simulated
        FROM   test_results
        WHERE  status = ?
        ORDER  BY id DESC
        LIMIT  ?
    """, (RESULT_OOS, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_oos_results():
    """
    Count of OOS results — used as a KPI metric on the dashboard.
    A single COUNT(*) is much faster than fetching all rows and len()-ing them.
    """
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM test_results WHERE status = ?", (RESULT_OOS,)
    ).fetchone()[0]
    conn.close()
    return count
