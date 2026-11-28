# ADR 0020: Pages query only what they show; a benchmark keeps it that way

- **Status:** Accepted (2026-11-28)
- **Addresses:** roadmap item 4.2; audit findings M1 and M3.

## Context
A new benchmark, `scripts/benchmark.py`, renders every page through the real app against a throwaway database. At 10,000 samples and 11,706 results, before this change:

| Page | Cold render | Why |
|---|---|---|
| Test Results | 9,164 ms | M1: one query, and one cache entry, per sample to build "View All Results" |
| Reports | 225 ms | loaded every sample and result to count and chart them, then filtered in Python |
| Admin | 103 ms | loaded every sample to count them and the FDA imports |

Every other page was already under 50 ms: Sample Tracking (ADR 0016) and the Audit Trail were already paged in SQL.

## Decision
- **Test Results:**
  - `repo.results.find_results(status, limit, offset)` returns one page of 100 results in a single JOIN with the sample, review and investigation, plus the total;
  - the tab has a page number, and changing the filter goes back to page 1;
  - the Log tab gets its samples from `loggable_samples(username)` in SQL. `domain.result_entry_error` still applies, and `services.record_result` still enforces it.
- **Reports:**
  - the figures, OOS breakdown and monthly trend come from SQL aggregates (`report_summary`), which use the OOS category CASE from ADR 0019;
  - full rows load only when an export is generated (`get_report_rows`, not cached, since it can be large);
  - the status and priority filters run in SQL (`repo.samples.report_filter`). An empty selection matches nothing, as before.
- **Admin:** the counts come from `COUNT ... GROUP BY`.
- **Removed:** `get_all_samples`, `get_all_results` and `get_results_for_sample` had no callers left. Leaving them in would invite the next N+1.
- **M3, cache coherence:** every service write already clears its caches, the FDA import included (ADR 0002 and the service layer). The new cached queries are added to `clear_data_caches`. Coherence across several app processes needs a shared database and is left to Phase 5 (C2).
- **Guards:**
  - `tests/test_queries.py` counts the SELECTs the Test Results page runs. The count must be the same for 10 and 300 samples. Against the 3.8 code it fails: 16 against 306;
  - a 300-sample benchmark run is part of the suite;
  - run the full benchmark with `python scripts/benchmark.py` (budget 1 s per page; it exits non-zero when a page is over).

## Result (10,000 samples, cold cache)
| Page | Before | After |
|---|---|---|
| Test Results | 9,164 ms | 73 ms |
| Reports | 225 ms | 85 ms |
| Admin | 103 ms | 24 ms |

## Consequences
- **Exports still hold every selected row in memory.** That is what the file contains. At 10,000 samples it takes seconds, not minutes; streaming is unnecessary at this scale.
- **The timings come from AppTest on a developer laptop.** They don't include the browser or network, and the in-suite benchmark uses a generous limit because CI machines vary.
