# ADR 0014: Second-person review of results with e-signature

- **Status:** Accepted (2026-11-27)
- **Addresses:** roadmap item 3.3 (audit H5 "no review", results workflow gap; 21 CFR Part 11 §11.50, §11.70, §11.200).
- **Builds on:** ADR 0011 (lifecycle), 0012 (specifications), 0013 (password security).

## Context
A result counted as soon as the analyst logged it. Nobody else checked it, and a sample could be completed on unverified data. The audit's acceptance criterion: *a result counts toward release only after a different user signs (password re-entry plus meaning).*

## Decision (the product owner chose each policy)
- **Who signs: anyone except the analyst who logged the result** (admin or lab tech). No new role.
  - This is enforced in `domain.review_error`, in `services.sign_result`, and by a database trigger (`result_signatures_second_person`).
- **What a signature is:** a row in `result_signatures` (migration 7).
  - Each holds the result, the signer, the meaning (`Approved` or `Rejected`), the reason and the UTC time.
  - One signature per result.
  - Append-only: triggers reject UPDATE and DELETE.
  - The database also requires a reason for a rejection.
  - The meaning is stated to the signer in words ("Reviewed and approved — the result is valid…"), per §11.50.
- **Signing re-checks the password** through the same check as sign-in (`services._check_password`). Wrong passwords are audited as `SIGNATURE_FAILED` and count toward the lockout (ADR 0013).
  - A failed attempt is committed before the signature is refused.
  - Signing is allowed only while the sample is In Progress.
  - Each signature is audited as `RESULT_APPROVED` or `RESULT_REJECTED`, with old value "Awaiting review", the new value and the reason.
- **Completion needs review:** In Progress → Completed requires `unreviewed_count = 0` and `approved_count ≥ 1` (`repo.samples.REVIEW_COUNTS`, `domain.transition_error`).
- **Rejection invalidates; it doesn't edit.** The rejected result stays visible with its signature and reason, and no longer counts. The analyst logs a new result. Results are never edited or deleted.
- **Results already recorded:** existing results have no signature.
  - On In Progress samples they show "Awaiting review" and must be signed before completion.
  - On other samples (e.g. the 226 demo samples completed before this change) they show "Not reviewed" and stay as recorded.

## Consequences
- Every sample needs two people to complete. A lab with one active user can't complete samples.
- **Known gap until 3.4, OOS investigations:** a reviewer can reject an OOS result and the analyst can retest until it passes. This is "testing into compliance", which an inspector would look for. Until 3.4, the rejection is signed and needs a reason, and the OOS result stays on record and in the OOS counts and reports. 3.4 must require a closed investigation before an OOS result can be invalidated.
- A user locked out by wrong signature passwords stays signed in to their current session but can't sign or sign in again until the lock expires.
