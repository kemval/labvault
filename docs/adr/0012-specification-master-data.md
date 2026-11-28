# ADR 0012: Specification master data

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit finding H4d; roadmap item 3.2.

## Context
The analyst typed the acceptance limits with every result, so they effectively decided their own pass or fail, and the same test on the same kind of sample could be judged against different limits.

## Decision
- **Key: sample type × test**, decided with the product owner. The audit suggested product × test, but openFDA product names are effectively unique per sample (248 names across 255 samples), so per-product specifications would be one per sample.
- **Migration 5:** a `specifications` table holding limits, unit and `version`.
  - Database constraints: at least one limit, min ≤ max, and one row per sample type × test.
  - `test_results` gains `spec_id` and `spec_version`.
- **Old results are kept as recorded.** Their link is NULL and the results table shows "as recorded". Nothing historical is re-evaluated.
- **The service decides.** `services.record_result` takes the value or outcome, never limits.
  - It looks up the current specification inside the transaction and evaluates with `domain.evaluate_result`.
  - It stores a copy of the limits and the spec id and version.
  - Limits sent by a caller are ignored.
- **No specification, no numeric result.** Entry is blocked with "ask an admin", per the product owner's decision. Pass/fail tests (Label Review, Other) need no specification; "Other" is now pass/fail only.
- **Maintenance:** `services.save_specification` is admin only.
  - Creating writes `SPEC_CREATED`.
  - Changing needs a reason and the version being edited (optimistic locking), bumps the version and writes `SPEC_UPDATED` with old and new limits.
  - Specifications are never deleted, because results reference them.
- **Defaults:** `repo.specifications.DEFAULT_SPECS` are seeded **only in demo mode**. They are the limits the simulated data uses, and a test keeps the two in step. A secure deployment starts empty; acceptance limits are a QA decision.

## Consequences
- Admins must define a specification before the first numeric result of each sample type × test.
- The demo defaults include a sterility limit of 0 CFU/mL for injectables only. Non-sterile microbial limits (e.g. TAMC per USP <61>/<1111>) are left for QA to define.
- Product-level overrides can be added later as a more specific key, without changing how results record what judged them.
