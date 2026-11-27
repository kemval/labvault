# ADR 0006 — Streamlit-free persistence layer

- **Status:** Accepted (2026-11-27). Refines ADR 0005; ADR 0002's import
  logic is unchanged but has moved.
- **Addresses:** audit findings A2 (`db.py` did everything and imported
  Streamlit) and A3 (the seeder bypassed the data layer and its cache
  invalidation)

## Context
`db.py` held the connection, schema, migrations, auth, audit, every query,
the default protocol content and the Streamlit caches. Persistence could
not be used or tested without Streamlit. `seed.py` wrote raw SQL and had to
remember to clear caches itself.

## Decision
| Layer | Responsibility | May import Streamlit? |
|---|---|---|
| `views/`, `app.py` | Rendering, input | yes |
| `services.py` | Use cases. Each data change and its audit row in one transaction, then cache invalidation. Includes `import_fda()` and `log_event()` | only via `db` |
| `db.py` | `st.cache_data` wrappers around repo reads, plus `clear_*` invalidation. No writes | yes |
| `repo/` | SQL: `core` (connection, `transaction`), `schema` (migrations), `users`, `audit`, `samples`, `results`, `protocols`, `fda_import` | **no** |
| `seed.py` | openFDA fetch, parsing and simulation. No database access | **no** |
| `scripts/` | Maintenance CLIs on `repo/` and `seed` | **no** |

- `config.py` imports Streamlit lazily, only when reading `st.secrets`, so
  `repo.users` can raise `ConfigError` without it.
- View-facing read names (`db.get_all_samples` etc.) are unchanged.

## Enforcement
`tests/test_layering.py`:
- runs `repo/`, `seed` and `scripts/` end to end in a fresh interpreter and
  fails if `streamlit` was imported;
- fails if any view contains `INSERT`, `UPDATE` or `DELETE` SQL.

## Consequences
- New queries go in `repo/`. A read the views need gets a cached wrapper in
  `db.py`. A new write gets a function in `services.py` that clears the
  caches it affects.
- Tests use the `fresh_db` handle (`tests/conftest.py`). It patches
  `repo.core.DB_PATH` and clears caches after repo writes made through it.
