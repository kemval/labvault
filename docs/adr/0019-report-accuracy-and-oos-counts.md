# ADR 0019: Report accuracy and how OOS results are counted

- **Status:** Accepted (2026-11-28)
- **Addresses:** roadmap item 3.8; audit finding M9. Follows ADR 0015, whose consequences noted that invalidated OOS results were still counted.

## Context
- **Truncated PDF:** the PDF stopped at 50 samples and 30 OOS results, while its header stated the full totals.
- **"None" limits:** one-sided limits printed as "None – 110.0".
- **No context:** reports didn't say what they covered, who generated them, or how many pages they had.
- **Counts:** every OOS result ever recorded was counted as a failure, including ones an investigation had shown to be laboratory errors.

## Decision (the product owner chose to split the count)
- **OOS categories:** `domain.oos_category` puts each OOS result in one of four:

  | Category | Rule | Counted in totals? |
  |---|---|---|
  | **Confirmed** | the investigation concluded "OOS confirmed" | yes |
  | **Under investigation** | the investigation is open | yes |
  | **Not investigated** | recorded before investigations existed (migration 8 backfilled only In Progress samples) | yes |
  | **Invalidated (lab error)** | the investigation found an assignable laboratory error, or a reviewer rejected the result | no |

  - **Headline totals exclude invalidated results:** this applies to the dashboard KPI, the Admin panel and Reports. The breakdown is shown alongside, and invalidated results are still listed in reports, so nothing is hidden.
  - **Dashboard alerts:** the list leaves out invalidated results and shows each result's category.
  - **The same rule in SQL:** `repo.results.OOS_CATEGORY_SQL` repeats the rule for the counts, built from the same constants. A test checks that the SQL and Python versions agree on every kind of result.
- **The PDF:**
  - it contains every filtered sample and every OOS result. Tables repeat their headers on each page, and long names wrap instead of being cut;
  - a "Report covers" block states the UTC time, the user, the status and priority filters, the counts, the OOS breakdown and the database schema version;
  - every page carries a footer with the generation time and user, and "Page x of y" (a canvas that holds pages until the total is known);
  - limits read "90 – 110 %", "min 80 %" or "max 0 CFU/mL". Words are used instead of ≥ and ≤, which the PDF's standard fonts can't draw;
  - stored values are escaped before reportlab parses them as markup.
- **Excel:** a new first sheet, "Report Info", carries the same metadata. Results and OOS sheets gain the OOS status, the review and the investigation conclusion.
- **Reports page:**
  - the filters come first;
  - the metrics describe the selection that will be exported;
  - a monthly line chart shows results tested against OOS results counted.
- **A test safeguard found along the way:** a builder called without a database fixture opened the developer's `./labvault.db`. It only read from it, and the data was verified unchanged. `report_meta` is now pure (the caller passes in the schema version), and an autouse fixture, `never_the_real_database`, points every test at a temporary path.

## Consequences
- A full report of the development data is now 17 pages instead of 2 pages that silently dropped rows.
- Reports still load all samples and results, then filter in Python. Moving that to SQL is part of 4.2.
- There's no app version number to print. The database schema version stands in until releases are versioned.
