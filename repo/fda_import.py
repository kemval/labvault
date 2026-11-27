"""
repo/fda_import.py — write a parsed openFDA batch (ADR 0002).
"""

from datetime import datetime

from repo.core import get_conn


def write_batch(parsed: list, skipped: int, only_if_empty: bool = False) -> dict:
    """
    Store (sample, results) pairs from seed.parse_records in one transaction.
    Results are written only for samples that are actually new; with
    only_if_empty=True the write is skipped if any samples exist, checked
    under the write lock. Returns the import summary dict.
    """
    if not parsed:
        # Nothing to insert (maybe all records were malformed) — still a "success"
        return {"success": True, "count": 0, "already_present": 0,
                "skipped": skipped, "error": None}

    # ── Phase 2: one atomic transaction — single DB open/close ──
    # BEGIN IMMEDIATE takes SQLite's write lock up front, so the emptiness
    # check below and the inserts can't interleave with another session's
    # import (even one in a different process).
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        if only_if_empty and conn.execute("SELECT 1 FROM samples LIMIT 1").fetchone():
            # Another session imported while we were fetching — nothing to do.
            conn.rollback()
            return {"success": True, "count": 0, "already_present": 0,
                    "skipped": skipped, "error": None, "not_needed": True}

        # Insert samples one at a time so we know which ones are new.
        # Records already in the DB (or repeated within this batch) are ignored,
        # and their simulated results must be dropped too — otherwise every
        # re-import would attach a second set of results to existing samples.
        inserted_ids = set()
        new_results = []
        for s, results in parsed:
            cur = conn.execute("""
                INSERT OR IGNORE INTO samples
                    (sample_id, product_name, lot_number, manufacturer, sample_type,
                     recall_class, priority, reason_for_recall, collection_date,
                     status, assigned_to, protocol_id, notes, source, is_simulated)
                VALUES
                    (:sample_id, :product_name, :lot_number, :manufacturer, :sample_type,
                     :recall_class, :priority, :reason_for_recall, :collection_date,
                     :status, :assigned_to, :protocol_id, :notes, :source, 1)
            """, s)
            if cur.rowcount == 1:
                inserted_ids.add(s["sample_id"])
                new_results.extend(results)

        if new_results:
            conn.executemany("""
                INSERT INTO test_results
                    (sample_id, test_name, result_value, result_unit,
                     spec_min, spec_max, status, tested_by, tested_at, notes, is_simulated)
                VALUES
                    (:sample_id, :test_name, :result_value, :result_unit,
                     :spec_min, :spec_max, :status, :tested_by, :tested_at, :notes, 1)
            """, new_results)

        already_present = len(parsed) - len(inserted_ids)

        # One summary audit entry instead of one per record — 100 individual
        # entries would flood the audit trail and make it unreadable.
        conn.execute("""
            INSERT INTO audit_trail (timestamp, user, action, module, target_id, detail)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "system", "SAMPLE_IMPORTED", "FDA Seed", "bulk",
            f"Imported {len(inserted_ids)} new FDA recall records with "
            f"{len(new_results)} test results ({already_present} already present, "
            f"{skipped} skipped)."
        ))

        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        # Always close the connection — even if something explodes above
        conn.close()
    # ─────────────────────────────────────────────────────────

    return {
        "success":         True,
        "count":           len(inserted_ids),
        "already_present": already_present,
        "skipped":         skipped,
        "error":           None,
    }
