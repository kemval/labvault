"""Error alerts to ntfy: content, rate limits, failure safety (roadmap 5.3, ADR 0025)."""
import http.server
import logging
import threading

import pytest

import alerts
import logs


@pytest.fixture
def ntfy(monkeypatch):
    """A stand-in ntfy server that records what it receives."""
    received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            received.append({"path": self.path, "headers": dict(self.headers), "body": body})
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LABVAULT_DOMAIN", "lab.example.org")
    yield f"http://127.0.0.1:{server.server_address[1]}/labvault-topic", received
    server.shutdown()


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def logged_error(handler, message="The PDF report could not be built.", secret="lot 42"):
    logger = logging.getLogger("labvault.test-alerts")
    logger.addHandler(handler)
    try:
        try:
            raise RuntimeError(f"traceback detail: {secret}")
        except RuntimeError:
            logger.error(message, exc_info=True,
                         extra={"error_id": "3f9c1a2b", "context": {"user": "kembly"}})
    finally:
        logger.removeHandler(handler)


@pytest.mark.logs_errors
def test_an_alert_has_the_message_and_reference_but_no_details(ntfy):
    url, received = ntfy
    logged_error(alerts.AlertHandler(url, background=False))
    [alert] = received
    assert alert["path"] == "/labvault-topic"
    assert alert["headers"]["Title"] == "lab.example.org: error"
    assert alert["headers"]["Priority"] == "high"
    assert "The PDF report could not be built." in alert["body"]
    assert "Reference: 3f9c1a2b" in alert["body"]
    for private in ("lot 42", "traceback", "kembly", "RuntimeError"):
        assert private not in alert["body"]


@pytest.mark.logs_errors
def test_repeats_are_held_back_for_ten_minutes(ntfy):
    url, received = ntfy
    clock = Clock()
    handler = alerts.AlertHandler(url, clock=clock, background=False)
    for _ in range(5):
        logged_error(handler)                                # a fault on every rerun
    assert len(received) == 1
    logged_error(handler, message="Something went wrong on this page.")
    assert len(received) == 2                                # a different error still alerts
    clock.now = alerts.REPEAT_AFTER_S + 1
    logged_error(handler)
    assert len(received) == 3


@pytest.mark.logs_errors
def test_at_most_twenty_alerts_an_hour(ntfy):
    url, received = ntfy
    clock = Clock()
    handler = alerts.AlertHandler(url, clock=clock, background=False)
    for i in range(30):
        logged_error(handler, message=f"error {i}")
    assert len(received) == alerts.MAX_PER_HOUR
    clock.now = 3601
    logged_error(handler, message="after an hour")
    assert len(received) == alerts.MAX_PER_HOUR + 1


@pytest.mark.logs_errors
def test_a_broken_alert_channel_never_breaks_the_app(capsys):
    handler = alerts.AlertHandler("http://127.0.0.1:1/topic", background=False)
    logged_error(handler)                                    # must not raise
    assert "alert not delivered" in capsys.readouterr().err


def test_alerts_are_off_unless_configured(monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(logs.log, "handlers", [])
    logs.configure()
    assert not any(isinstance(h, alerts.AlertHandler) for h in logs.log.handlers)


def test_configure_attaches_one_alert_handler(monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(logs.log, "handlers", [])
    monkeypatch.setenv("LABVAULT_ALERT_URL", "https://ntfy.sh/some-long-topic")
    logs.configure()
    logs.configure()
    assert [type(h) for h in logs.log.handlers] == [alerts.AlertHandler]


def test_the_send_test_alert_script(ntfy, monkeypatch, capsys):
    from scripts import send_test_alert as test_alert
    url, received = ntfy
    monkeypatch.setenv("LABVAULT_ALERT_URL", url)
    monkeypatch.setenv("LABVAULT_ALERT_TOKEN", "tk_secret")
    assert test_alert.main() == 0
    [alert] = received
    assert alert["headers"]["Title"] == "lab.example.org: test alert"
    assert alert["headers"]["Authorization"] == "Bearer tk_secret"
    monkeypatch.delenv("LABVAULT_ALERT_URL")
    assert test_alert.main() == 1 and "alerts are off" in capsys.readouterr().err
