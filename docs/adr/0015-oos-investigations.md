# ADR 0015: OOS investigations

- **Status:** Accepted (2026-11-27)
- **Addresses:** roadmap item 3.4. Closes the "testing into compliance" gap left by ADR 0014. FDA guidance *Investigating OOS Test Results for Pharmaceutical Production*.

## Context
An OOS result was only a red flag. After 3.3, a reviewer could reject an OOS result and the analyst could retest until a result passed, with no investigation. FDA's guidance says an OOS result may be invalidated only when an investigation finds an assignable laboratory cause.

## Decision (the product owner chose who closes and what to backfill)
- **Every OOS opens an investigation.**
  - `services.record_result` inserts it in the same transaction as the result and audits `OOS_INVESTIGATION_OPENED`.
  - The FDA demo import does the same for simulated OOS results on In Progress samples.
- **Migration 8** creates `oos_investigations` and backfills one, opened by `system`, for each unsigned OOS result on an In Progress sample. This was 21 on the development database. OOS results on other samples stay as recorded.
- **Database guards:**
  - CHECKs: an open investigation has no conclusion; a closed one has a conclusion, a closer, a time and findings.
  - Triggers: no DELETE; a closed investigation can't be changed; the result and opening fields can't be changed; the result's own analyst can't close it.
- **Closing:** `services.close_investigation` is admin only (admins act as QA), never on a result the admin logged.
  - It is e-signed with the password check shared by sign-in (ADR 0013). Wrong passwords count toward the lockout.
  - A conclusion and written findings are required.
  - It is audited as `OOS_INVESTIGATION_CLOSED` (old value "Open", new value the conclusion, the findings as the reason).
- **The conclusion decides the signature** (`domain.allowed_meanings`):
  - while the investigation is open, the OOS result can't be signed at all, so its sample can't complete;
  - *Assignable laboratory error* means the result can only be **rejected**, and the analyst retests;
  - *OOS confirmed* means the result can only be **approved**, so the failure stands and the sample completes with it.

## Consequences
- An admin is needed before any sample with an OOS result can complete. An OOS result logged by an admin needs a second admin to close its investigation.
- **Simplified relative to FDA's guidance:**
  - one investigation record instead of Phase I (laboratory) and Phase II (full-scale, manufacturing);
  - no retest plan or averaging rules;
  - no CAPA link.
  These are noted as future work.
- OOS counts and reports still include every OOS result, invalidated or not. Report accuracy is 3.8.
