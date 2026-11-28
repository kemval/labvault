"""
repo/specifications.py — specification master data: acceptance limits per
sample type × test (migration 5, ADR 0012).
"""

from domain import SYSTEM_USER
from repo.core import get_conn, run_in, utc_now

# Demo defaults, seeded only in demo mode: the limits the simulated FDA
# results already use. A real lab's QA defines its own on the Specifications page.
DEFAULT_SPECS = (
    # (sample types, test, min, max, unit)
    (("Tablet", "Capsule", "Injectable", "Liquid", "Topical", "Powder"),
     "Potency (% Label Claim)", 90.0, 110.0, "%"),
    (("Tablet", "Capsule"), "Dissolution (60 min)", 80.0, None, "%"),
    (("Liquid", "Injectable", "Topical"), "pH", 4.5, 7.5, "pH"),
    (("Injectable",), "Visible Particulates", 0.0, 10.0, "particles/container"),
    (("Injectable",), "Sterility / Microbial Count", 0.0, 0.0, "CFU/mL"),
)


def find_spec(sample_type: str, test_name: str, conn=None):
    """The current specification for sample type × test, or None."""
    def run(c):
        row = c.execute("SELECT * FROM specifications WHERE sample_type = ? AND test_name = ?",
                        (sample_type, test_name)).fetchone()
        return dict(row) if row else None
    return run_in(conn, run)


def all_specs():
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM specifications ORDER BY sample_type, test_name")]
    finally:
        conn.close()


def insert_spec(conn, sample_type, test_name, spec_min, spec_max, unit, user) -> int:
    return conn.execute("""
        INSERT INTO specifications (sample_type, test_name, spec_min, spec_max, unit,
                                    updated_by, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (sample_type, test_name, spec_min, spec_max, unit, user, utc_now())).lastrowid


def update_spec(conn, spec_id, expected_version, spec_min, spec_max, unit, user) -> bool:
    """Bump the version; False if it changed since `expected_version`."""
    return conn.execute("""
        UPDATE specifications
        SET spec_min = ?, spec_max = ?, unit = ?, version = version + 1,
            updated_by = ?, updated_at = ?
        WHERE id = ? AND version = ?
    """, (spec_min, spec_max, unit, user, utc_now(), spec_id, expected_version)).rowcount == 1


def seed_specifications():
    """Demo mode only: load DEFAULT_SPECS if no specification exists yet."""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM specifications LIMIT 1").fetchone() is None:
            for types, test, lo, hi, unit in DEFAULT_SPECS:
                for sample_type in types:
                    insert_spec(conn, sample_type, test, lo, hi, unit, SYSTEM_USER)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
