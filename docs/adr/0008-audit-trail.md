# ADR 0008: Complete, append-only audit trail

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit finding C3 (b), (c), (d), (f), (g) and (h); roadmap item 2.5.
- **Earlier parts:** (a) atomic writes came in ADR 0005; (e) user references in ADR 0007.

## Decision
- **Structured changes (b).** Migration 4 adds `old_value`, `new_value` and `reason` to `audit_trail`.
  - `services.update_sample` writes one row per changed field, with all three.
  - A real change without a reason is refused (`ServiceError`) and nothing is written. Saving with no change needs no reason.
  - Creating a record needs no reason; the record itself is the new value.
- **UTC (c).** New rows use `repo.core.utc_now()`, ISO-8601 with `Z`. Rows written before migration 4 keep the local time they were recorded with: rewriting audit history would defeat its purpose. The two formats are distinguishable, and ordering uses `id`, not `timestamp`.
- **Append-only (d).** `BEFORE UPDATE` / `BEFORE DELETE` triggers raise "audit_trail is append-only". This applies to every connection, including ad-hoc scripts.
  - The triggers don't protect against someone with file access deleting or replacing the database; backups (`docs/operations/backup-restore.md`) and hosting access controls cover that.
  - A future migration that must rebuild `audit_trail` has to drop and recreate the triggers inside its own transaction.
- **Attribution (f).** `services.import_fda(user=…)` credits the admin who clicked Import, or the user whose first login triggered the automatic import. `system` remains only for unattended work: migrations and default data.
- **Events (g).**
  - `services.sign_in` writes `LOGIN`, or `LOGIN_FAILED`. A failure is credited to the account when it exists, otherwise to `system`, with the attempted name (max 64 characters) as the target.
  - `services.sign_out` writes `LOGOUT`.
  - `REPORT_EXPORTED` is written by the download button's callback, when the file leaves the app, not when it is generated.
- **Reachability (h).** The audit page filters and pages in SQL (`repo.audit.search_audit`), 100 rows per page. The action filter lists the actions present in the data.
- **The dashboard feed** leaves out sign-in events, which would otherwise push data changes off it.

## Consequences
- Every status or assignment change needs a typed reason.
- The trail grows with every sign-in. Paging by primary key keeps the page fast; retention is a policy decision for later.
