"""The dependency gate's exceptions file (roadmap 4.4, ADR 0022)."""
from datetime import date

import pytest

from scripts.audit_deps import EXCEPTIONS, ExceptionsError, read_exceptions

TODAY = date(2026, 11, 28)


def test_valid_entries_and_comments():
    text = """
    # header comment
    GHSA-aaaa-bbbb-cccc  2026-12-31  no fix released; affected API unused
    PYSEC-2026-1  2026-11-28  until the next release   # due today: still valid
    """
    assert read_exceptions(text, TODAY) == ["GHSA-aaaa-bbbb-cccc", "PYSEC-2026-1"]


def test_an_expired_exception_fails():
    with pytest.raises(ExceptionsError, match="GHSA-old.*expired on 2026-11-27"):
        read_exceptions("GHSA-old  2026-11-27  waiting for a fix", TODAY)


@pytest.mark.parametrize("line", ["GHSA-x", "GHSA-x 2026-12-31", "GHSA-x 31/12/2026 why",
                                  "GHSA-x 2026-13-01 why"])
def test_entries_need_an_id_a_date_and_a_reason(line):
    with pytest.raises(ExceptionsError, match="line 1"):
        read_exceptions(line, TODAY)


def test_the_committed_file_is_valid_today():
    with open(EXCEPTIONS, encoding="utf-8") as f:
        read_exceptions(f.read(), date.today())
