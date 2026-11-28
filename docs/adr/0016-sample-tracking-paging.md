# ADR 0016: Sample Tracking as a paged table with one detail panel

- **Status:** Accepted (2026-11-27)
- **Addresses:** roadmap item 3.5; audit findings M2, U3 and U7 (in part).

## Context
Sample Tracking loaded every sample, filtered in Python and drew each one as an expander with two selectboxes, a text input and a button: about 765 widgets at 255 samples, growing linearly. There was no sort, no "my samples" view and no confirmation before ending a sample's lifecycle, and the assigned protocol was never shown.

## Decision
- **Filtering, search, sorting and paging run in SQL.** `repo.samples.find_samples` returns one page (25 rows) and the match count.
  - Search matches the sample ID or product name case-insensitively. `%`, `_` and `\` are escaped so they match literally.
  - The sorts are newest first (the old order), priority with Critical first, collection date with oldest first, and sample ID. Each ends on the row id, so pages are stable.
  - The **Show** filter offers All samples, Assigned to me, and Unassigned. Unassigned helps lab techs find samples they can claim.
  - Changing any filter returns to page 1.
- **One read-only table plus one detail panel.** The user picks a sample from the current page in an "Open sample" selectbox. A selectbox is keyboard-accessible and testable with AppTest, where dataframe row selection isn't. The detail panel loads only that sample through `sample_detail`, including its review counts and its protocol's name.
  - A sample that leaves the page through a filter or paging closes instead of pointing at a hidden row.
- **The edit form is unchanged in its rules:** the permitted statuses and assignees from `domain`, a reason, and the optimistic version check with Reload.
- **Moving a sample to Rejected or Completed needs a confirmation tick.** Save stays disabled until it is ticked, because only an admin can reopen the sample. This is a UI safeguard; the services enforce the rules themselves.
- Notes are rendered as plain text, not markdown.

## Consequences
- The page renders a constant number of widgets. At 5,000 samples, a page change re-renders in under 2 s in the test suite, and the query cost is a COUNT plus a LIMIT/OFFSET on indexed columns.
- Opening a sample takes one extra click compared with expanding a card.
- **Not done:**
  - deep links to a sample (`st.query_params`);
  - editing the protocol after intake;
  - due dates and SLA indicators.
  These stay in the backlog. Other pages still use `get_all_samples`; their query work is 4.2.
