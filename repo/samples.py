"""
repo/samples.py — sample rows.
"""

from config import ConfigError
from domain import PRIORITIES, REVIEW_APPROVED, STATUS_IN_PROGRESS, TERMINAL_STATUSES
from repo.core import get_conn, run_in


def insert_sample(data: dict, conn=None) -> bool:
    """
    Insert a sample row; returns False if the sample_id already exists.
    Only that conflict is ignored — invalid values raise IntegrityError
    (INSERT OR IGNORE would silently drop them too). Pass `conn` to join the caller's transaction — the
    caller then clears caches after commit. App code should use
    services.register_sample, which also writes the audit row.
    """
    def run(c):
        return c.execute("""
            INSERT INTO samples
                (sample_id, product_name, lot_number, manufacturer, sample_type,
                 recall_class, priority, reason_for_recall, collection_date,
                 status, assigned_to, protocol_id, notes, source)
            VALUES
                (:sample_id, :product_name, :lot_number, :manufacturer, :sample_type,
                 :recall_class, :priority, :reason_for_recall, :collection_date,
                 :status, :assigned_to, :protocol_id, :notes, :source)
            ON CONFLICT (sample_id) DO NOTHING
        """, data).rowcount == 1

    return run_in(conn, run)


# Per-sample result counts for the completion rule (domain.transition_error):
# all results, approved ones, and ones nobody has signed yet.
REVIEW_COUNTS = f"""
    (SELECT COUNT(*) FROM test_results t
     WHERE t.sample_id = samples.sample_id) AS result_count,
    (SELECT COUNT(*) FROM test_results t JOIN result_signatures g ON g.result_id = t.id
     WHERE t.sample_id = samples.sample_id AND g.meaning = '{REVIEW_APPROVED}') AS approved_count,
    (SELECT COUNT(*) FROM test_results t LEFT JOIN result_signatures g ON g.result_id = t.id
     WHERE t.sample_id = samples.sample_id AND g.id IS NULL) AS unreviewed_count"""


# The orders the tracking page offers. Every one ends on id so paging is stable.
_PRIORITY_RANK = "CASE priority " + " ".join(
    f"WHEN '{p}' THEN {i}" for i, p in enumerate(PRIORITIES)) + f" ELSE {len(PRIORITIES)} END"
SAMPLE_SORTS = {
    "newest":     "samples.id DESC",
    "priority":   f"{_PRIORITY_RANK}, samples.id DESC",
    "collection": "collection_date, samples.id",
    "sample_id":  "sample_id, samples.id",
}

# Only what the tracking table shows; the detail panel loads the full row.
_LIST_COLUMNS = ("sample_id, product_name, status, priority, assigned_to, "
                 "collection_date, sample_type, is_simulated")


def _like(text: str) -> str:
    """A LIKE pattern matching `text` literally anywhere (\\ escapes % and _)."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def find_samples(status=None, priority=None, search="", assigned_to=None,
                 unassigned=False, sort="newest", limit=25, offset=0):
    """
    One page of samples for the tracking table, filtered and sorted in SQL,
    plus the number of matches: (rows, total). `assigned_to` keeps one
    user's samples; `unassigned` keeps those with no assignee. `search`
    matches the sample ID or product name, case-insensitively.
    """
    where, args = [], []
    if status:
        where.append("status = ?")
        args.append(status)
    if priority:
        where.append("priority = ?")
        args.append(priority)
    if search.strip():
        where.append("(sample_id LIKE ? ESCAPE '\\' OR product_name LIKE ? ESCAPE '\\')")
        args += [_like(search.strip())] * 2
    if unassigned:
        where.append("assigned_to IS NULL")
    elif assigned_to:
        where.append("assigned_to = ?")
        args.append(assigned_to)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    order = SAMPLE_SORTS[sort]
    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) FROM samples{clause}", args).fetchone()[0]
    rows = conn.execute(f"SELECT {_LIST_COLUMNS} FROM samples{clause} "
                        f"ORDER BY {order} LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def report_filter(statuses=None, priorities=None, alias="samples"):
    """(WHERE clause, args) over `alias` for the report filters. None means
    any; an empty list matches nothing, as an empty multiselect should."""
    where, args = [], []
    for column, values in (("status", statuses), ("priority", priorities)):
        if values is not None:
            where.append(f"{alias}.{column} IN ({', '.join('?' * len(values)) or 'NULL'})")
            args += list(values)
    return (f"WHERE {' AND '.join(where)}" if where else ""), args


def report_samples(statuses=None, priorities=None):
    """Every sample matching the report filters, newest first."""
    where, args = report_filter(statuses, priorities)
    conn = get_conn()
    rows = conn.execute(f"SELECT * FROM samples {where} ORDER BY id DESC", args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def loggable_samples(username=None):
    """In Progress samples a user can log results on: those assigned to
    `username`, or all of them when None (admins). domain.result_entry_error
    is the rule; services.record_result enforces it."""
    where, args = "status = ?", [STATUS_IN_PROGRESS]
    if username is not None:
        where += " AND assigned_to = ?"
        args.append(username)
    conn = get_conn()
    rows = conn.execute(f"SELECT sample_id, product_name, sample_type, status, assigned_to, "
                        f"is_simulated FROM samples WHERE {where} ORDER BY id DESC",
                        args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_by_source():
    """{source: count}, e.g. how many samples came from the FDA import."""
    conn = get_conn()
    rows = conn.execute("SELECT source, COUNT(*) AS n FROM samples GROUP BY source").fetchall()
    conn.close()
    return {r["source"]: r["n"] for r in rows}


def open_samples_assigned(conn, username: str) -> list:
    """IDs of samples assigned to `username` that are not Completed or Rejected."""
    marks = ", ".join("?" * len(TERMINAL_STATUSES))
    return [r[0] for r in conn.execute(
        f"SELECT sample_id FROM samples WHERE assigned_to = ? AND status NOT IN ({marks}) "
        "ORDER BY sample_id", (username, *TERMINAL_STATUSES))]


def sample_detail(sample_id: str):
    """
    One sample with what the tracking detail panel needs: the review counts
    (for the completion rule) and its protocol's name. None if it doesn't exist.
    """
    conn = get_conn()
    row = conn.execute(f"""
        SELECT samples.*, {REVIEW_COUNTS}, p.name AS protocol_name
        FROM samples LEFT JOIN protocols p ON p.id = samples.protocol_id
        WHERE samples.sample_id = ?""", (sample_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def recent_samples(limit: int = 8):
    """
    Only fetches the columns
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


def refuse_simulated_data():
    """
    For non-demo deployments: raise ConfigError if the database holds any
    simulated sample or result, so demo data can never become production
    records (roadmap 5.4, ADR 0026). Called once at start-up.
    """
    found = count_simulated()
    if found["samples"] or found["results"]:
        raise ConfigError(
            f"This database contains simulated demo data ({found['samples']} samples, "
            f"{found['results']} test results). A non-demo deployment must start from a "
            "fresh database (LABVAULT_DB_PATH); never promote a demo database.")


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
