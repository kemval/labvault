# ADR 0028: Signatures shown wherever a signed result is shown or printed

- **Status:** Accepted (2026-11-28)
- **Addresses:** the gap found while drafting the validation package (ADR 0027): 21 CFR 11.50 and Annex 11 §14. Requirement ESG-05.
- **Builds on:** ADR 0014 (result review as an electronic signature).

## Context
21 CFR 11.50 requires a signed electronic record, when displayed or printed, to show the signer's printed name, the date and time of signing, and the meaning of the signature. LabVault stored all of that (`result_signatures`), but:
- the PDF's OOS table showed no signature;
- the Excel OOS sheet had none, and the results sheet had no time or reason;
- the results page showed "Approved by X" without the time.

## Decision
- **`views.ui.signature_text(r)`** is the one readable form: "Approved by alice, 2026-11-28 07:53:25 UTC", plus ": reason" for a rejection. The results page and the PDF use it. An unsigned OOS result prints "Not signed".
- **Excel** keeps the parts as separate columns (Signature, Signed By, Signed At (UTC), Signature Reason) on both the results and OOS sheets, so they can be filtered.
- **PDF side margins are now 40 pt,** matching the footer, to fit the new column. The data still comes from the existing report query; no schema change.

## Consequences
- Every signed result that appears on screen or in an export carries its signature details. Tests cover all three outputs.
- Exports gain columns; anything parsing the Excel by column position must be updated. Nothing in the repository does.
