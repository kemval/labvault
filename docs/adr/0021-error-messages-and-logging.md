# ADR 0021: Plain error messages with a reference; JSON logs with the traceback

- **Status:** Accepted (2026-11-28)
- **Addresses:** roadmap item 4.3; audit finding M8.

## Context
Raw exception text reached users in three places:
- the Excel and PDF exports showed `f"... failed: {e}"`;
- the FDA import returned `str(e)`, which the sidebar and the first-login import displayed. That text included hostnames, URLs and proxy details.

Any other uncaught exception showed Streamlit's default error box with the full traceback. Nothing was logged in a form an operator could search: the app had no logging configuration, and only `seed.py` logged at all.

`ServiceError` messages are written for users (for example "Reason is required"), so they are shown as they are. The `ConfigError` message tells the operator what to set, so it is shown too.

## Decision
- **`logs.py`:**
  - `configure()` installs one JSON-lines handler on stderr, once per process. LabVault's loggers log from INFO; other libraries only from WARNING.
  - `log_exception(message, **context)` logs the exception being handled, with its traceback, under a new 8-hex-digit `error_id`, and returns that id.
- **`views.ui.show_error(message, **context)`:** shows `message`, a request to try again, and the reference. The exports use it.
- **`services.import_fda`:** a fetch failure returns "the openFDA service could not be reached or sent an unexpected response (reference …)". A successful import logs an INFO line with its counts.
- **App-wide handler:** the main flow in `app.py` runs in `main()` inside `try/except Exception`. A failure shows "Something went wrong on this page." with a reference, and the next interaction runs normally. A non-`ConfigError` failure during setup shows "LabVault could not start." `st.rerun()` and `st.stop()` raise `BaseException` subclasses, so they pass through.
- **Fallback:** `client.showErrorDetails = "none"` in `.streamlit/config.toml` covers anything that escapes the handler, such as widget callbacks. The browser then shows Streamlit's generic message.
- **Tests:**
  - the handler hides crashes from AppTest's `at.exception`, so an autouse fixture (`logged_errors` in `tests/conftest.py`) fails any test in which LabVault logs an error, unless the test is marked `@pytest.mark.logs_errors`;
  - a deliberate page crash in an unmarked test was checked to fail.

## Consequences
- A user can quote a reference, and an operator can `grep` the log for it.
- Log lines contain usernames and record context, and may contain data values in tracebacks. Logs need the same access control as the database.
- Shipping logs to a monitoring service, with alerting, is roadmap 5.3.
- Local developers also see no traceback in the browser; it is in the terminal as JSON.
