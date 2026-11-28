"""No exception text in the UI; tracebacks logged under a reference (audit M8, ADR 0021)."""
import json
import logging
import os
import tomllib

import pytest

import db
import logs
from test_app_login import APP, go, login, no_network, run_app  # noqa: F401

SECRET = "/srv/labvault/private.db is locked"


def boom(*_args, **_kwargs):
    raise RuntimeError(SECRET)


def shown(at) -> str:
    return " ".join(e.value for e in at.error)


@pytest.mark.logs_errors
def test_failed_export_shows_a_reference_not_the_exception(open_sample, settings, monkeypatch,
                                                           logged_errors):
    settings(demo="true")
    at = go(login(run_app(), "kembly", "lab2024"), "Reports")
    monkeypatch.setattr(db, "get_report_rows", boom)
    [excel] = [b for b in at.button if "Generate Excel" in b.label]
    excel.click().run()

    [logged] = logged_errors
    assert "The Excel report could not be built." in shown(at)
    assert logged.error_id in shown(at)
    assert SECRET not in shown(at) and "RuntimeError" not in shown(at)
    assert logged.context == {"user": "kembly", "action": "excel_export"}
    assert repr(logged.exc_info[1]) == repr(RuntimeError(SECRET))


@pytest.mark.logs_errors
def test_a_crashing_page_shows_a_reference_and_the_app_keeps_working(lab_db, settings,
                                                                     monkeypatch,
                                                                     logged_errors):
    settings(demo="true")
    at = login(run_app(), "kembly", "lab2024")
    with monkeypatch.context() as fault:
        fault.setattr(db, "count_simulated", boom)       # read by app.py on every page
        at.run()

    [logged] = logged_errors
    assert not at.exception                               # no traceback reaches the browser
    assert "Something went wrong on this page." in shown(at)
    assert logged.error_id in shown(at) and SECRET not in shown(at)
    assert logged.context == {"user": "kembly"}

    at.run()                                              # the fault is gone: so is the error
    assert not at.error and at.session_state.logged_in


def test_log_lines_are_json_with_reference_and_traceback(logged_errors):
    try:
        boom()
    except RuntimeError:
        ref = logs.log_exception("Export failed", user="kembly")
    record = logged_errors.pop()                          # handled: the guard sees none
    line = logs.JsonFormatter().format(record)
    assert "\n" not in line                               # one record per line
    entry = json.loads(line)
    assert (entry["level"], entry["message"], entry["error_id"]) == ("ERROR", "Export failed",
                                                                     ref)
    assert entry["context"] == {"user": "kembly"}
    assert SECRET in entry["traceback"] and entry["time"].endswith("Z")


def test_configure_installs_one_handler(monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    logs.configure()
    logs.configure()                                      # every rerun calls it
    assert len(root.handlers) == 1
    assert logging.getLogger(logs.LOGGER).isEnabledFor(logging.INFO)


def test_streamlit_never_shows_error_details():
    # Covers what escapes app.py's handler, such as button callbacks.
    with open(os.path.join(os.path.dirname(APP), ".streamlit", "config.toml"), "rb") as f:
        assert tomllib.load(f)["client"]["showErrorDetails"] == "none"
