# ADR 0004 — Flag and mark simulated demo data

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit finding C4 (simulated results indistinguishable from real records)

## Context
The FDA import stores real recall records with an invented lot number,
assignee and lab status, plus fully simulated test results. Notes such as
"Superpotency confirmed" and `tested_by` set to a real lab tech made the
simulated records look like genuine QC data. Nothing distinguished them from
results logged by hand.

## Decision
1. Migration 1 (ADR 0003) adds `is_simulated INTEGER NOT NULL DEFAULT 0` to
   `samples` and `test_results`, so manual entries are real by default.
2. Backfill:
   - every `source = 'FDA'` sample is flagged;
   - a result is flagged only if it belongs to an FDA sample **and** its notes
     match `seed.SIMULATOR_NOTES`, so anything logged by hand against a demo
     sample stays real;
   - the backfill writes a `SCHEMA_MIGRATED` audit entry.
3. New imports set the flag, record `tested_by = "simulator"`
   (`seed.SIMULATOR_USER`), and say so in the sample notes.
4. Existing rows keep their original `tested_by`. Rewriting historical
   attribution in place would itself be an unaudited change to records; the
   flag is what marks them.
5. The data is marked wherever it is shown or exported:
   - a notice on every page while any simulated data exists;
   - a SIMULATED badge on dashboard cards and Sample Tracking;
   - a "Simulated" column in the results tables, the dashboard OOS table and
     all three Excel sheets;
   - a count line and `*`-marked Sample IDs in the PDF.

## Consequences
- `seed.SIMULATOR_NOTES` is the single source of the simulator's wording. A
  test fails if `simulate_test_results()` produces a note it doesn't match.
- Keeping simulated data out of production entirely (refusing to run the
  importer in secure mode) is roadmap item 5.4.
