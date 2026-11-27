# ADR 0005 — Transactional service layer and optimistic concurrency

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit findings A1 (no service layer), C3a (audit row written
  separately from the change), H8 (lost updates), L6 (silent ID-collision drop)

## Context
Each view called separate `db.py` helpers that committed on their own
connection, followed by `log_action`, which committed on another. Saving a
sample could take 4 commits. A failure in between left data changed without
an audit row. Two users editing the same sample overwrote each other
silently.

## Decision
1. **`services.py`** holds one function per use case: `register_sample`,
   `update_sample`, `record_result` and `create_protocol`. Each runs in a
   single `db.transaction()` (`BEGIN IMMEDIATE`, commit or roll back) that
   includes its audit row, written with `db.write_audit(conn, …)`. Caches are
   cleared only after commit. Views never write to the database directly.
2. **`db.py` insert helpers take an optional `conn`**, so they can join a
   caller's transaction. Called without one, they run in their own (used by
   test fixtures and scripts). `log_action` remains only for events that
   change no data, such as report exports.
3. **Optimistic concurrency.** Migration 2 adds `samples.version`.
   - `update_sample(sample_id, expected_version, …)` re-reads the row under
     the write lock. If the version differs it raises
     `ConcurrentUpdateError` and writes nothing. Otherwise it updates with
     `version = version + 1` and records old → new values in the audit.
   - A no-op save writes nothing.
   - A rejected update clears caches so a reload shows the current data.
4. **The UI tracks the version the form was opened with.** Streamlit reruns
   the whole script on every click and re-reads the sample before the click
   is handled, so the freshly read version can't be used for the check. The
   edit widgets already keep what the user first saw. Sample Tracking stores
   the matching version in `st.session_state` next to them, resets both
   together after a save or an explicit **Reload form**, and warns when the
   sample changed underneath an open form.
5. **Sample IDs.** `register_sample` owns ID generation and retries on a
   collision instead of silently dropping the sample.

## Consequences
- New write paths must go through `services.py`. Code review should reject
  any `INSERT`, `UPDATE` or `DELETE` in `views/`.
- Only samples are versioned. Results and protocols are insert-only today.
  Add versions to them when they gain edit or correction workflows (roadmap
  3.3).
- The FDA import and the maintenance scripts keep their own single
  transactions (ADR 0002, `scripts/`).
