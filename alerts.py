"""
alerts.py — push error alerts to the owner via ntfy (roadmap 5.3, ADR 0025).

Every ERROR that LabVault logs (logs.log_exception, ADR 0021) is also sent as
a push notification to an ntfy topic (https://ntfy.sh or a self-hosted ntfy):

    LABVAULT_ALERT_URL    https://ntfy.sh/<long-unguessable-topic>   (unset: no alerts)
    LABVAULT_ALERT_TOKEN  optional access token for a protected topic

An alert carries only the message, the error reference, the time and the
instance name: never the traceback, the user or any record data, which stay in
the server log. One alert per distinct message per 10 minutes, and at most 20
an hour, so one fault cannot flood the phone. Sending happens in a background
thread with a short timeout; a broken alert channel never affects the app.
"""

import logging
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

REPEAT_AFTER_S = 600       # the same message again only after 10 minutes
MAX_PER_HOUR = 20
TIMEOUT_S = 5


def alert_url():
    return (os.environ.get("LABVAULT_ALERT_URL") or "").strip() or None


def instance_name() -> str:
    return (os.environ.get("LABVAULT_DOMAIN") or "").strip() or "LabVault"


def send(title: str, body: str, *, priority: str = "high", tags: str = "warning",
         url: str = None, token: str = None) -> None:
    """POST one ntfy message. Raises OSError on failure (callers decide)."""
    url = url or alert_url()
    if not url:
        raise OSError("LABVAULT_ALERT_URL is not set")
    headers = {"Title": title, "Priority": priority, "Tags": tags}
    token = token if token is not None else os.environ.get("LABVAULT_ALERT_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers,
                                     method="POST")
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as resp:
        if resp.status >= 300:
            raise OSError(f"ntfy answered {resp.status}")


class AlertHandler(logging.Handler):
    """Logging handler: ERROR records become rate-limited ntfy alerts."""

    def __init__(self, url: str, clock=time.monotonic, background: bool = True):
        super().__init__(level=logging.ERROR)
        self.url = url
        self.clock = clock
        self.background = background
        self._last_by_message = {}
        self._sent = []          # send times within the last hour
        self._lock = threading.Lock()

    def _allowed(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            self._sent = [t for t in self._sent if now - t < 3600]
            last = self._last_by_message.get(key)
            if (last is not None and now - last < REPEAT_AFTER_S) or \
                    len(self._sent) >= MAX_PER_HOUR:
                return False
            self._last_by_message[key] = now
            self._sent.append(now)
            return True

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if not self._allowed(message):
            return
        ref = getattr(record, "error_id", None)
        when = datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        body = f"{message}\nReference: {ref or '—'}\nTime: {when}\n" \
               f"Details: search the server log for the reference."
        title = f"{instance_name()}: error"
        if self.background:
            threading.Thread(target=self._deliver, args=(title, body), daemon=True).start()
        else:
            self._deliver(title, body)

    def _deliver(self, title: str, body: str) -> None:
        try:
            send(title, body, url=self.url)
        except Exception as e:      # never let alerting break or recurse into logging
            print(f"labvault alert not delivered: {e!r}", file=sys.stderr)
