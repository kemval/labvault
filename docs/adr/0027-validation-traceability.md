# ADR 0027: Requirements, risk and traceability generated from one source and checked in CI

- **Status:** Accepted (2026-11-28)
- **Addresses:** roadmap item 5.5 (Computer System Validation package), lightweight scope agreed with the owner.

## Context
A GxP lab system needs documented requirements, a risk assessment and evidence that each requirement is verified. LabVault has over 400 automated tests and 26 ADRs, but nothing that says which requirement each one proves. Hand-written traceability goes stale as soon as a test is renamed.

The full validation package also includes executed IQ/OQ/PQ, SOPs and signed approvals. That only means something when a regulated lab executes and signs it on its own system. Writing it now would mean inventing dates, signatures and executions.

## Decision
- **One source:** `docs/validation/requirements.toml`. Each requirement has an id, area, statement, regulation references, GAMP 5 risk ratings (impact, likelihood, detectability), its controls, its ADRs and its tests.
- **`scripts/traceability.py` generates** the requirements specification, the risk assessment (GAMP 5 risk class and priority) and the traceability matrix in `docs/validation/`.
- **CI enforces it.** `tests/test_traceability.py` runs `--check`, which fails if a requirement has no test, names a test or ADR that doesn't exist, has invalid ratings, or a generated document is out of date. Renaming or deleting a traced test therefore fails the build until the trace is updated.
- **Tests are referenced by name from the TOML, not by markers in the test files.** That keeps the requirement wording and its evidence in one reviewable place, and leaves the test code unchanged.
- **Every document is marked DRAFT, not an executed validation.** `validation-plan.md` lists what the lab must still do, plus the known gaps found while writing the requirements.

## Consequences
- 45 requirements are traced: 22 High, 14 Medium and 9 Low priority.
- **Gap found:** reports don't show signature details (21 CFR 11.50). It's recorded in the plan, not fixed here.
- Adding a requirement or test means editing the TOML and running the script; CI says if it's forgotten.
- Python 3.11+ is required for `tomllib`, which is already the minimum CI version.
