"""
Container health check (roadmap 5.2, ADR 0024). Exit 0 when healthy.

Healthy means Streamlit answers its health endpoint and the database opens
and reports a schema version. Read-only: it never writes or migrates.

    python scripts/healthcheck.py      # uses PORT and LABVAULT_DB_PATH
"""

import os
import sqlite3
import sys
import urllib.request


def check(port: int, db_path: str, timeout: float = 3.0) -> list[str]:
    """Problems found; an empty list means healthy."""
    problems = []
    try:
        # Local call: never through a proxy configured in the environment.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=timeout) as resp:
            if resp.status != 200:
                problems.append(f"app health endpoint returned {resp.status}")
    except OSError as e:
        problems.append(f"app not answering on port {port}: {e}")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
        try:
            if conn.execute("PRAGMA user_version").fetchone()[0] < 1:
                problems.append(f"{db_path} has no schema yet")
        finally:
            conn.close()
    except sqlite3.Error as e:
        problems.append(f"database {db_path} not readable: {e}")
    return problems


def main() -> int:
    problems = check(int(os.environ.get("PORT", "8501")),
                     os.environ.get("LABVAULT_DB_PATH", "labvault.db"))
    for p in problems:
        print(f"unhealthy: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
