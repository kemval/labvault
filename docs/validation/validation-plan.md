# LabVault validation plan (outline)

> **DRAFT — not an executed validation.** Nothing here has been executed, reviewed or
> approved by a regulated organisation, and no signatures or dates are implied. This
> outline says what exists and what a lab would still have to do before using LabVault
> for GxP records. Roadmap 5.5, ADR 0027.

## 1. System and approach
- **System:** LabVault, a QC laboratory system covering samples, results against specifications, second-person review with electronic signatures, OOS investigations, the audit trail and reports. Production runs as the container in ADR 0024, with continuous off-site replication (ADR 0023).
- **GAMP 5 category 5** (custom software). The lab is the regulated user; the developer is the supplier.
- **Risk-based** (GAMP 5, 2nd ed.; FDA *Computer Software Assurance*, 2025). The verification effort for each requirement follows its priority in the [risk assessment](risk-assessment.md):

| Priority | Before go-live |
|---|---|
| High | Automated tests (exist), plus scripted testing on the lab's qualified system, with recorded evidence |
| Medium | Automated tests (exist), plus unscripted or exploratory testing on the lab's system |
| Low | Automated tests (exist); supplier evidence accepted |

## 2. What exists (supplier deliverables)

| Deliverable | Where |
|---|---|
| Requirements specification, 45 requirements tied to 21 CFR 11, 21 CFR 211, EU GMP Annex 11 and ALCOA+ | [requirements-specification.md](requirements-specification.md) |
| Risk assessment (GAMP 5 method) | [risk-assessment.md](risk-assessment.md) |
| Traceability, requirement → ADR → automated test; CI fails if any requirement is untraced | [traceability-matrix.md](traceability-matrix.md) |
| Design decisions | `docs/adr/` (ADR 0001–0027) |
| Automated test suite, run on every change on Python 3.11 and 3.12 | `tests/`, `.github/workflows/ci.yml` |
| Installation and recovery evidence: container build, backup, destroy, restore and verify | `deploy/smoke_test.sh`, `.github/workflows/container.yml` |
| Operations runbooks: deployment, durable storage and restore drill, monitoring, dependency policy | `docs/operations/` |

## 3. What the lab must still do
1. **Validation plan and approvals.** Adopt or rewrite this outline under the lab's own quality system, and name the system owner, process owner and QA approver.
2. **Review the requirements and risks.** QA confirms that the requirements match the lab's process and re-rates the risks. The ratings in this draft are the developer's.
3. **Supplier assessment** of the developer: the development process, version control, CI, and how defects are handled.
4. **Installation qualification (IQ)** on the lab's server. Record the image digest, host, volume, replica bucket, TLS certificate, time synchronisation (NTP) and the environment settings, with secrets excluded. Run `deploy/smoke_test.sh` against the lab's environment.
5. **Operational qualification (OQ).** Run the automated suite against the release being validated and keep the report. Execute scripted tests for every High-priority requirement on the qualified system, with screenshots or exports as evidence.
6. **Performance qualification (PQ).** Run the lab's real workflow with trained users and the lab's own specifications: intake → result → review and signature → OOS investigation → report.
7. **SOPs:**
   - user access management: requesting, approving and periodically reviewing accounts;
   - backup and restore, including the quarterly restore drill in `docs/operations/durable-storage.md`;
   - audit trail review;
   - incident and deviation handling, using error references and alerts (ADR 0021, ADR 0025);
   - change control and release, using PRs, CI and the image digest;
   - data retention and archiving;
   - business continuity.
8. **Training** of users and administrators, with records kept.
9. **Validation summary report** and release for use.
10. **Periodic review,** for example yearly: the dependency audit, access review, restore drill results and the deviations log.

## 4. Known gaps to resolve or accept before go-live
- **Signatures are not shown on reports.** The Excel and PDF exports list samples and results but not who signed each result, when, or the meaning of the signature. 21 CFR 11.50 requires printed signed records to show all three.
- **Single instance.** SQLite with one writer (ADR 0023). A deployment must never run two app containers against the same replica.
- **No production deployment exists yet.** The hosting decision is open, so IQ cannot start.
- **Time source.** Timestamps come from the server clock in UTC (DAT-03). The host's time synchronisation must be qualified in IQ.
- **Retention.** Replicas keep 30 days of history (ADR 0023). Long-term archiving of records and audit trail isn't implemented; the retention SOP must define it.
- **Demo and production separation** is enforced (ADR 0026). The public demo must never be used for real records.
