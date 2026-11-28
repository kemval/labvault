"""
logs.py — structured logging and error references (audit M8, ADR 0021).

Users never see exception text. They see a plain message with a short
reference; the traceback goes to the log under the same reference, so an
administrator can find it:

    try:
        ...
    except Exception:
        ref = log_exception("Excel export failed", user="kembly")
        st.error(f"The report could not be built. Reference: {ref}.")

Log lines are JSON objects on stderr (one per line), which Streamlit
Community Cloud and container platforms collect as they are:

    {"time": "2026-11-28T10:15:02.114Z", "level": "ERROR", "logger": "labvault",
     "message": "Excel export failed", "error_id": "3f9c1a2b",
     "context": {"user": "kembly"}, "traceback": "Traceback ..."}
"""

import json
import logging
import sys
import uuid
from datetime import datetime, timezone

LOGGER = "labvault"
log = logging.getLogger(LOGGER)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc)
                            .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("error_id", "context"):
            if getattr(record, key, None):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["traceback"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class _StderrHandler(logging.StreamHandler):
    """Writes to whatever sys.stderr is now. A handler that kept the stream it
    was created with would write to a closed file once a test runner swaps
    stderr."""

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value):
        pass


def configure() -> None:
    """
    Send log records to stderr as JSON, once per process (safe to call on
    every rerun). LabVault's own loggers log from INFO; other libraries only
    from WARNING.
    """
    root = logging.getLogger()
    if any(isinstance(h, _StderrHandler) for h in root.handlers):
        return
    handler = _StderrHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.WARNING:
        root.setLevel(logging.WARNING)
    log.setLevel(logging.INFO)


def log_exception(message: str, **context) -> str:
    """
    Log the exception being handled, with its traceback, under a new
    reference, and return the reference for the user's message. Call it
    from an `except` block. `context` (user, page, …) is logged with it.
    """
    error_id = uuid.uuid4().hex[:8]
    log.error(message, exc_info=True, extra={"error_id": error_id, "context": context})
    return error_id
