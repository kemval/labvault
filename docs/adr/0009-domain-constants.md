# ADR 0009: Domain values defined once

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit findings TD1, TD2, TD5, TD6 and TD9; roadmap item 2.6.

## Decision
- **`domain.py`** defines every stored domain value: sample statuses, priorities, recall classes, sample types (plus "Non-sterile" for protocols), sources, result statuses, roles, and the `system`/`simulator` accounts.
  - Every layer imports from it, including SQL, which takes the values as parameters.
  - It imports nothing from the app, so `repo/` and `seed` stay free of Streamlit.
- **Plain string constants and tuples, not `Enum`.** The values are what the database stores and what Streamlit widgets display, so plain `str` needs no conversion at either boundary.
- **Migration 3 keeps its own frozen copy** (ADR 0007), because a released migration must never change. `tests/test_domain.py` asserts the two are equal. Adding, renaming or removing a value therefore means:
  1. a new migration that changes the CHECK constraint (and converts existing rows when renaming);
  2. updating `domain.py`;
  3. updating the test to compare against the new migration's copy.
- **Smaller changes:**
  - `views/ui.page_header()` replaces the copied header HTML, and escapes its arguments.
  - `app.PAGES` drives both the sidebar and routing.
  - A duplicated PDF style rule is removed. It was always painted over, so the output is unchanged.
  - The seeder logs each skipped record and the reason. A record with an unreadable recall date is now skipped instead of being given today's date.
