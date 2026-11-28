"""
Dependency vulnerability gate (roadmap 4.4, ADR 0022).

Runs pip-audit on both hashed lock files. Any known vulnerability fails,
except one listed in .github/audit-exceptions.txt, and an exception past its
review-by date fails as well, so it is looked at again:

    .venv/bin/python scripts/audit_deps.py

Exceptions file, one per line (# starts a comment):

    GHSA-xxxx-xxxx-xxxx  2027-01-31  no fixed release yet; we don't call the affected API
"""

import os
import re
import subprocess
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEPTIONS = os.path.join(ROOT, ".github", "audit-exceptions.txt")
LOCKS = ("requirements.txt", "requirements-dev.txt")
LINE = re.compile(r"^(?P<id>\S+)\s+(?P<review>\d{4}-\d{2}-\d{2})\s+(?P<reason>\S.*)$")


class ExceptionsError(ValueError):
    """The exceptions file is malformed or has an expired entry."""


def read_exceptions(text: str, today: date) -> list[str]:
    """IDs to ignore. Raises ExceptionsError for a bad line or an expired entry."""
    ids, problems = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = LINE.match(line)
        if not m:
            problems.append(f"line {n}: expected 'ID  YYYY-MM-DD  reason', got {raw!r}")
            continue
        try:
            review = date.fromisoformat(m["review"])
        except ValueError:
            problems.append(f"line {n}: {m['review']} is not a date")
            continue
        if review < today:
            problems.append(f"line {n}: the exception for {m['id']} expired on {review}; "
                            "review it, then remove it or set a new date")
        ids.append(m["id"])
    if problems:
        raise ExceptionsError("\n".join(problems))
    return ids


def main(today: date | None = None) -> int:
    try:
        with open(EXCEPTIONS, encoding="utf-8") as f:
            ignored = read_exceptions(f.read(), today or date.today())
    except FileNotFoundError:
        ignored = []
    except ExceptionsError as e:
        print(f"error: {os.path.relpath(EXCEPTIONS, ROOT)}:\n{e}", file=sys.stderr)
        return 1
    if ignored:
        print("Ignoring (see .github/audit-exceptions.txt):", ", ".join(ignored))
    failed = False
    for lock in LOCKS:
        print(f"── pip-audit {lock}", flush=True)
        cmd = [sys.executable, "-m", "pip_audit", "-r", os.path.join(ROOT, lock),
               "--require-hashes", "--strict", "--progress-spinner", "off", "--desc", "on",
               *[arg for vuln in ignored for arg in ("--ignore-vuln", vuln)]]
        failed |= subprocess.run(cmd).returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
