"""Production packaging: health check, image contents and secrets (roadmap 5.2, ADR 0024).
The image itself is built and tested end to end by deploy/smoke_test.sh in CI."""
import http.server
import os
import threading

import pytest

from repo import core
from scripts import healthcheck

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def health_server():
    """A stand-in for Streamlit's /_stcore/health endpoint."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            ok = self.path == "/_stcore/health"
            self.send_response(200 if ok else 404)
            self.end_headers()
            self.wfile.write(b"ok" if ok else b"")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


def test_healthy_when_the_app_answers_and_the_database_has_a_schema(fresh_db, health_server):
    assert healthcheck.check(health_server, core.DB_PATH) == []


def test_unhealthy_when_the_app_is_down(fresh_db, health_server):
    [problem] = healthcheck.check(1, core.DB_PATH, timeout=0.5)       # nothing on port 1
    assert "app not answering" in problem


def test_unhealthy_without_a_database_and_never_creates_one(tmp_path, health_server):
    missing = tmp_path / "labvault.db"
    [problem] = healthcheck.check(health_server, str(missing))
    assert "not readable" in problem and not missing.exists()          # read-only


def test_image_never_contains_local_data_or_secrets():
    ignored = read(".dockerignore").split()
    for pattern in ("labvault.db", "labvault.db-*", "labvault.db.backup-*", "*.db",
                    ".streamlit/secrets.toml", "deploy/.env", ".env", ".git"):
        assert pattern in ignored


def test_image_verifies_litestream_and_runs_unprivileged():
    dockerfile = read("Dockerfile")
    assert 'sha256sum -c -' in dockerfile
    assert "USER labvault" in dockerfile and "--require-hashes" in dockerfile
    assert 'HEALTHCHECK' in dockerfile and 'ENTRYPOINT ["deploy/start.sh"]' in dockerfile


def test_secrets_stay_out_of_the_repository():
    assert "deploy/.env" in read(".gitignore").split()
    example = read("deploy", ".env.example")
    assert "AWS_SECRET_ACCESS_KEY=\n" in example                       # empty placeholders
    for name in ("compose.yaml", "Caddyfile"):
        text = read("deploy", name)
        assert "SECRET" not in text and "PASSWORD=" not in text


def test_no_usage_statistics_leave_the_server():
    import tomllib
    config = tomllib.loads(read(".streamlit", "config.toml"))
    assert config["browser"]["gatherUsageStats"] is False
