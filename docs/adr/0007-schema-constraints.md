# ADR 0007: Schema constraints, user references and timestamps

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit finding M4, roadmap item 2.4. Builds on ADR 0003 (migrations).

## Context
The database accepted any value in `status`, `priority`, `role` and similar
columns. Names in `assigned_to`, `tested_by`, `created_by` and the audit trail
were free text, so a typo or a deleted account left records pointing at
nobody. Rows had no record of when they were created or last changed.

## Decision
Migration 3 (`repo/schema.py`) rebuilds the five tables with constraints.

- **Value rules (CHECK):**
  - users: role ∈ admin / lab_tech / system;
  - samples: status, priority, recall class, sample type, source, `is_simulated` ∈ {0, 1}, `version` ≥ 1;
  - results: status, and `spec_min` ≤ `spec_max`;
  - protocols: sample type.
  - The allowed values are frozen copies inside the migration, so a released migration never changes.
- **User references (FOREIGN KEY → `users.username`):** `samples.assigned_to` (NULL means unassigned), `test_results.tested_by`, `protocols.created_by` and `audit_trail.user`. A referenced account can't be deleted; removing access will mean disabling it (roadmap 3.6).
- **System accounts:** `system` (imports, migrations, default protocols) and `simulator` (simulated results).
  - They have role `system` and a password value that can never match a hash.
  - `authenticate()` also refuses the role.
  - They don't count as "users exist" for first-run seeding.
  - If a human account already uses one of these names, the migration stops.
- **Timestamps:** `samples.created_at` / `updated_at` and `test_results.created_at`, in UTC ISO-8601 (`…Z`), with database defaults. `update_sample` sets `updated_at`. Existing rows keep NULL, meaning "not recorded"; no time is invented.
- **Fail closed:** before rebuilding, the migration lists every existing value that would break a rule. If any is found it raises `MigrationError` and changes nothing, not even the system accounts. After copying it runs `PRAGMA foreign_key_check`. Everything runs in the one migration transaction.
- **No invented names:** with no lab techs, imports leave samples unassigned. The intake and tracking pages offer "Unassigned".

## Consequence: `INSERT OR IGNORE` removed
`OR IGNORE` also suppresses CHECK and NOT NULL failures, so invalid rows would have disappeared silently. Sample inserts now use `ON CONFLICT (sample_id) DO NOTHING`, which ignores only the duplicate-ID case:
- Invalid values raise `IntegrityError`.
- The FDA import skips such records (for example openFDA's "Not Yet Classified") and counts them as `skipped`.

## Rehearsal
On a copy of the development database (255 samples, 286 results, 306 audit rows), migration 3 took 6 ms:
- every row and id was identical, with only the new columns added;
- the two system accounts were added;
- the foreign-key and integrity checks were clean.

## Rollback
Restore the pre-migration backup (`docs/operations/backup-restore.md`). Take one before deploying this change.
