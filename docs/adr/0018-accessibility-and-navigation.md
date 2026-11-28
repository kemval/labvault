# ADR 0018: Accessible navigation, keyboard sign-in and colour contrast

- **Status:** Accepted (2026-11-28)
- **Addresses:** roadmap item 3.7; audit findings U1 and U5, and U6 in part.

## Context
- **Navigation:** a sidebar radio with emoji labels such as "📊  Dashboard". Screen readers announce the emoji's name before each title, and pages had no URLs.
- **Sign-in:** pressing Enter in the sign-in fields did nothing.
- **Contrast:** several hard-coded text colours fell below the WCAG AA threshold of 4.5:1. The dashboard's `#aaa` was 2.3:1 and `#888` was 3.5:1, and the orange `#e65100` on the Pending and Major badges was 3.5:1.
- **Sidebar CSS:** `[data-testid="stSidebar"] * { color: … !important }` recoloured every element in the sidebar, including alerts and focus rings.

## Decision
- **`st.navigation`**, with the page table defined once in `views/navigation.py`.
  - Each view file is a page: it calls `show()` under `if __name__ == "__main__"`, and tests import it as a module as before.
  - Icons are Material Symbols, which Streamlit renders `aria-hidden`. Titles are plain text.
  - Pages are registered per role, so an admin-only page has no URL for a lab tech. The view also re-checks the role.
  - Every page now has a URL (for example `/sample_tracking`), and the browser's Back button works.
- **Sign-in is a form**, so pressing Enter submits it. The fields carry `autocomplete` hints for password managers.
- **Colours:**
  - `#aaa` and `#888` become `#595959` (7.0:1), and the 10–11 px text there becomes 12 px;
  - the orange badge text becomes `#bf360c` (5.1:1).
  - `tests/test_accessibility.py` checks every hard-coded text colour in `app.py` and `views/` against the background in the same rule or inline style, or white if there is none. It also checks the header subtitle with its opacity, and the theme colours.
- **Theme in `.streamlit/config.toml`:** the navy sidebar comes from `[theme.sidebar]` instead of the blanket CSS override.
  - `base = "light"` keeps the light-coloured cards readable when the visitor's OS prefers dark mode.
  - `.gitignore` now admits only this file from `.streamlit/`; `secrets.toml` stays ignored.
- **Decorative emoji are hidden:** the leading emoji in page headers and the sign-in logo are `aria-hidden`.
- **A header bug fixed along the way:** `.lv-header span` also matched the span Streamlit wraps around heading text, which shrank and dimmed every page title. The subtitle now has its own class.

## Consequences
- Tests navigate with `test_app_login.go(at, title)` (`AppTest.switch_page`). `registered_pages()` reads `AppTest._registered_pages`, a private attribute, in one helper.
- Opening a page's URL while signed out shows the sign-in page, and after signing in the user lands on the Dashboard, not the linked page.
- **Not done:**
  - emoji in section subheadings and buttons, which screen readers still read;
  - the `use_container_width` deprecation in the views (U8);
  - a full screen-reader audit.
