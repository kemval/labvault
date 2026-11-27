"""
One-off clean-up for audit finding C5: before the fix, re-importing FDA data
attached a second set of simulated test results to samples that already
existed.

For each FDA-imported sample, this keeps the first (lowest id) result per test
and deletes later results for the same test **only if** their notes match the
simulator's fixed wording (seed.simulate_test_results). Results logged by hand
are never touched.

Dry run by default. With --apply it first writes a backup next to the
database, then deletes in one transaction and records an audit entry.

    python scripts/dedupe_simulated_results.py labvault.db
    python scripts/dedupe_simulated_results.py labvault.db --apply --user admin
"""

import argparse
import re
import sqlite3
import sys
from datetime import datetime

# Every note template seed.simulate_test_results can produce.
SIMULATOR_NOTES = re.compile(
    r"^(?:"
    r"Within specification\."
    r"|Failed USP Apparatus II\. Result [\d.]+% below Q=80% specification\."
    r"|Superpotency confirmed\. Result [\d.]+% exceeds 110% upper limit\."
    r"|Subpotency confirmed\. Result [\d.]+% below 90% lower limit\."
    r"|Microbial contamination detected: \d+ CFU/mL\. Sterility failure\."
    r"|Visible particulate matter detected: \d+ particles/container\."
    r"|pH [\d.]+ outside specification range 4\.5–7\.5\."
    r"|Product potency within spec\. Recall due to labeling deficiency, not product failure\."
    r"|Label deficiency confirmed\. Missing or incorrect information identified\."
    r"|Result [\d.]+% below 90% specification\."
    r")$"
)


def find_duplicates(conn):
    """Return result rows that are later simulated copies of an earlier result."""
    rows = conn.execute("""
        SELECT t.id, t.sample_id, t.test_name, t.result_value, t.status, t.notes
        FROM test_results t
        JOIN samples s ON s.sample_id = t.sample_id
        WHERE s.source = 'FDA'
          AND t.id > (SELECT MIN(t2.id) FROM test_results t2
                      WHERE t2.sample_id = t.sample_id AND t2.test_name = t.test_name)
        ORDER BY t.sample_id, t.test_name, t.id
    """).fetchall()
    return [r for r in rows if SIMULATOR_NOTES.match(r[5] or "")]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("db_path")
    parser.add_argument("--apply", action="store_true", help="delete (default: dry run)")
    parser.add_argument("--user", help="username recorded in the audit trail (required with --apply)")
    args = parser.parse_args(argv)
    if args.apply and not args.user:
        parser.error("--user is required with --apply")

    conn = sqlite3.connect(args.db_path)
    try:
        dupes = find_duplicates(conn)
        for r in dupes:
            print(f"  id={r[0]:<6} {r[1]:<14} {r[2]:<30} {r[3]!s:<8} {r[4]}")
        print(f"{len(dupes)} duplicate simulated result(s) found.")

        if not dupes or not args.apply:
            if dupes:
                print("Dry run — nothing deleted. Re-run with --apply --user <name> to delete.")
            return 0

        backup_path = f"{args.db_path}.backup-{datetime.now():%Y%m%d-%H%M%S}"
        with sqlite3.connect(backup_path) as backup:
            conn.backup(backup)
        print(f"Backup written to {backup_path}")

        with conn:  # one transaction: deletes + audit entry, or nothing
            conn.executemany("DELETE FROM test_results WHERE id = ?", [(r[0],) for r in dupes])
            conn.execute("""
                INSERT INTO audit_trail (timestamp, user, action, module, target_id, detail)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), args.user,
                "RESULTS_DEDUPLICATED", "Maintenance", "bulk",
                f"Removed {len(dupes)} duplicate simulated test results created by "
                f"repeated FDA imports (audit C5). Backup: {backup_path}",
            ))
        print(f"Deleted {len(dupes)} row(s).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
