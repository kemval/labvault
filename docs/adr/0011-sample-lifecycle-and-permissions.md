# ADR 0011: Sample lifecycle and permissions

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit finding H5; roadmap item 3.1.
- **To be extended by:** 3.3 (review and e-signature) and 3.4 (OOS investigation).

## Context
Any lab tech could change any sample's status, including Completed → Pending; reassign any sample; and log results against any sample, even Rejected or Completed ones.

## Decision
- **Lifecycle on the existing four statuses** (`domain.TRANSITIONS`). The audit's longer target lifecycle needs review and OOS states that only make sense once 3.3 and 3.4 exist; those items will split Completed, with their own migration.

  | From | To | Who |
  |---|---|---|
  | Pending | In Progress, Rejected | assignee or admin |
  | In Progress | Completed (needs ≥ 1 recorded result), Rejected | assignee or admin |
  | Completed | In Progress (reopen) | admin |
  | Rejected | Pending (reopen) | admin |

- **Who may change a sample:**
  - an admin, or the lab tech it is assigned to;
  - a tech may claim an unassigned sample, and claim and start it in one change;
  - only admins assign to someone else or unassign;
  - assignees must be lab techs;
  - Completed and Rejected samples can't be reassigned unless they are reopened in the same change.
- **Results:** only while the sample is In Progress, by its assignee or an admin.
- **Reasons:** every change already needs one (ADR 0008), so a rejection or reopening is always explained.
- **One rule set, two uses.** The rules are pure functions in `domain.py`.
  - The pages use them to offer only allowed options; other people's samples are read-only.
  - `services.py` enforces them inside the write transaction, reading the actor's role, the assignee's role and the result count from the database. The caller can't claim a role.
  - Refusals raise `PermissionDeniedError`, a `ServiceError`, with a sentence the page shows as is.
  - System accounts can't change data.

## Consequences
- A tech must move a sample to In Progress before logging results.
- Admins act as supervisors: they can do everything a tech can, on any sample. A separate reviewer role arrives with 3.3.
