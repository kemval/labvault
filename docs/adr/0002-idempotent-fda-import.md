# ADR 0002 — Idempotent, race-safe FDA import

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit findings C5 (re-import duplicates results) and C6
  (first-run import retry loop and cross-session double import)

## Context
- **Duplicate results.** `seed_from_fda` inserted samples with
  `INSERT OR IGNORE` but inserted every simulated result unconditionally, so
  each re-import attached another result set to existing samples.
- **Retry loop.** A failed first-login import was retried on every rerun,
  blocking each interaction for up to 15 s.
- **Double import.** The "is the DB empty?" check went through a
  process-wide 60 s cache that the import never cleared, so a second session
  could import again.

## Decision
1. Each parsed sample stays paired with its simulated results. Samples are
   inserted one at a time, and results are written only for samples whose
   insert actually added a row (`cursor.rowcount == 1`). The returned
   `count` is the number of new samples; `already_present` is reported
   separately.
2. The write phase runs in one `BEGIN IMMEDIATE` transaction. With
   `only_if_empty=True` (used by the first-login auto-import), the emptiness
   check runs inside that transaction, under SQLite's write lock. A database
   lock is used instead of a Python lock because it also holds across
   processes.
3. The network fetch stays outside the transaction so the write lock is never
   held during I/O. The cost is a wasted fetch for a session that loses the
   race.
4. The import clears all data caches (`db.clear_data_caches()`) in `finally`.
5. The auto-import is attempted once per session, whether it succeeds or not.
   Failures are shown to the user; admins can retry from the sidebar.
6. Existing duplicates are removed by `scripts/dedupe_simulated_results.py`.
   It is a dry run by default. With `--apply` it backs up the database, then
   deletes and writes an audit entry in one transaction. It only deletes later
   results whose notes match the simulator's exact wording, so manually
   logged re-tests are kept.

## Consequences
- The admin "Import FDA Data" button stays additive (it imports a new batch),
  but it can no longer duplicate anything.
- Imports are still audited as user `system` (audit C3f, roadmap 2.5).
