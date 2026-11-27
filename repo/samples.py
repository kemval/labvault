"""
repo/samples.py — sample rows.
"""

from repo.core import get_conn, run_in


def insert_sample(data: dict, conn=None) -> bool:
    """
    Insert a sample row; returns False if the sample_id already exists
    (INSERT OR IGNORE). Pass `conn` to join the caller's transaction — the
    caller then clears caches after commit. App code should use
    services.register_sample, which also writes the audit row.
    """
    def run(c):
        return c.execute("""
            INSERT OR IGNORE INTO samples
                (sample_id, product_name, lot_number, manufacturer, sample_type,
                 recall_class, priority, reason_for_recall, collection_date,
                 status, assigned_to, protocol_id, notes, source)
            VALUES
                (:sample_id, :product_name, :lot_number, :manufacturer, :sample_type,
                 :recall_class, :priority, :reason_for_recall, :collection_date,
                 :status, :assigned_to, :protocol_id, :notes, :source)
        """, data).rowcount == 1

    return run_in(conn, run)


def all_samples(status_filter=None):
    """
    Fetch all samples, optionally filtered by status.
    The index on status makes the filtered query very fast even with many rows.
    """
    conn = get_conn()
    if status_filter and status_filter != "All":
        rows = conn.execute(
            "SELECT * FROM samples WHERE status = ? ORDER BY id DESC", (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM samples ORDER BY id DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def recent_samples(limit: int = 8):
    """
    A lightweight version of get_all_samples — only fetches the columns
    the dashboard actually needs, and only the N most recent rows.
    No point pulling all 100 columns × 100 rows just to show 8 cards.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT sample_id, product_name, manufacturer, status, priority, assigned_to, "
        "is_simulated "
        "FROM samples ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sample(sample_id: str):
    """Look up a single sample by its ID."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM samples WHERE sample_id = ?", (sample_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def count_samples_by_status():
    """
    GROUP BY query that returns a dict like {"Pending": 12, "Completed": 45, ...}.
    Used by the dashboard KPI cards and bar chart. Much cheaper than loading all rows.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT status, COUNT(*) as count FROM samples GROUP BY status
    """).fetchall()
    conn.close()
    return {r["status"]: r["count"] for r in rows}


def count_samples_by_priority():
    """Same pattern as count_samples_by_status but grouped by priority level."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT priority, COUNT(*) as count FROM samples GROUP BY priority
    """).fetchall()
    conn.close()
    return {r["priority"]: r["count"] for r in rows}


def count_simulated():
    """How much demo data the instance holds — drives the demo-data notice."""
    conn = get_conn()
    samples = conn.execute("SELECT COUNT(*) FROM samples WHERE is_simulated = 1").fetchone()[0]
    results = conn.execute("SELECT COUNT(*) FROM test_results WHERE is_simulated = 1").fetchone()[0]
    conn.close()
    return {"samples": samples, "results": results}


def sample_exists():
    """
    Quick boolean check — is there at least one sample in the DB?
    Used on startup to decide whether to run the auto-import.
    COUNT(*) on an indexed table is nearly instant.
    """
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    conn.close()
    return count > 0
