import threading

import pytest

import seed
import services
from fake_fda import record, serve


def counts(db):
    conn = db.get_conn()
    try:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("samples", "test_results", "audit_trail")}
    finally:
        conn.close()


def results_per_test(db):
    conn = db.get_conn()
    try:
        return conn.execute("""
            SELECT MAX(c) FROM (SELECT COUNT(*) c FROM test_results
                                GROUP BY sample_id, test_name)
        """).fetchone()[0]
    finally:
        conn.close()


def test_import_inserts_samples_and_results(fresh_db, monkeypatch):
    serve(monkeypatch, [record(1), record(2)])
    result = services.import_fda(limit=2)
    assert result["success"] and result["count"] == 2 and result["already_present"] == 0
    # A dissolution recall simulates two tests per sample.
    assert counts(fresh_db)["samples"] == 2
    assert counts(fresh_db)["test_results"] == 4


def test_reimport_of_same_records_adds_nothing(fresh_db, monkeypatch):
    serve(monkeypatch, [record(1), record(2)])
    services.import_fda(limit=2)
    before = counts(fresh_db)

    result = services.import_fda(limit=2)

    assert result["count"] == 0 and result["already_present"] == 2
    after = counts(fresh_db)
    assert after["samples"] == before["samples"]
    assert after["test_results"] == before["test_results"]
    assert after["audit_trail"] == before["audit_trail"] + 1  # the attempt is still audited


def test_overlapping_import_adds_only_new_samples_results(fresh_db, monkeypatch):
    serve(monkeypatch, [record(1), record(2)])
    services.import_fda(limit=2)
    serve(monkeypatch, [record(2), record(3)])
    result = services.import_fda(limit=2)

    assert result["count"] == 1 and result["already_present"] == 1
    assert counts(fresh_db)["samples"] == 3
    assert counts(fresh_db)["test_results"] == 6
    assert results_per_test(fresh_db) == 1


def test_duplicate_recall_within_one_batch_keeps_first_records_results(fresh_db, monkeypatch):
    # Same recall number twice, with different reasons → different simulated tests.
    serve(monkeypatch, [record(1, reason="Failed dissolution specifications"),
                        record(1, reason="Superpotent drug")])
    result = services.import_fda(limit=2)

    assert result["count"] == 1 and result["already_present"] == 1
    conn = fresh_db.get_conn()
    tests = sorted(r[0] for r in conn.execute("SELECT test_name FROM test_results"))
    conn.close()
    assert tests == ["Dissolution (60 min)", "Potency (% Label Claim)"]
    assert results_per_test(fresh_db) == 1


def test_only_if_empty_is_a_noop_when_samples_exist(fresh_db, monkeypatch):
    serve(monkeypatch, [record(1)])
    services.import_fda(limit=1)
    before = counts(fresh_db)

    serve(monkeypatch, [record(5), record(6)])
    result = services.import_fda(limit=2, only_if_empty=True)

    assert result["success"] and result["count"] == 0 and result.get("not_needed")
    assert counts(fresh_db) == before  # not even an audit entry


def test_concurrent_first_imports_import_once(fresh_db, monkeypatch):
    # Both "sessions" finish fetching before either writes — the worst case.
    barrier = threading.Barrier(2, timeout=10)
    serve(monkeypatch, [record(1), record(2)], before_return=barrier.wait)
    outcomes = []

    def first_login():
        outcomes.append(services.import_fda(limit=2, only_if_empty=True))

    threads = [threading.Thread(target=first_login) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert sorted(o["count"] for o in outcomes) == [0, 2]
    assert counts(fresh_db)["samples"] == 2
    assert results_per_test(fresh_db) == 1
    conn = fresh_db.get_conn()
    imports = conn.execute(
        "SELECT COUNT(*) FROM audit_trail WHERE action = 'SAMPLE_IMPORTED'").fetchone()[0]
    conn.close()
    assert imports == 1


def test_import_refreshes_cached_reads(fresh_db, monkeypatch):
    assert fresh_db.sample_exists() is False  # now cached as False
    serve(monkeypatch, [record(1)])
    services.import_fda(limit=1)
    assert fresh_db.sample_exists() is True
    assert fresh_db.get_oos_breakdown()["counted"] == 1


@pytest.mark.logs_errors
def test_api_failure_reports_error_and_writes_nothing(fresh_db, monkeypatch, logged_errors):
    def boom(*a, **k):
        raise ConnectionError("API down at 10.0.0.7")
    monkeypatch.setattr(seed.requests, "get", boom)

    result = services.import_fda()

    assert (result["success"], result["count"]) == (False, 0)
    assert counts(fresh_db) == {"samples": 0, "test_results": 0, "audit_trail": 0}
    # The user gets plain words and a reference; the details are only in the log (M8).
    [logged] = logged_errors
    assert "10.0.0.7" not in result["error"]
    assert f"reference {logged.error_id}" in result["error"]
    assert "API down at 10.0.0.7" in repr(logged.exc_info[1])


def test_unreadable_date_is_skipped_not_replaced_with_today(caplog):
    import seed
    from fake_fda import record
    bad = {**record(2), "recall_initiation_date": "2024-13-45"}
    with caplog.at_level("WARNING", logger="seed"):
        parsed, skipped = seed.parse_records([record(1), bad], ["kembly"])
    assert [s["sample_id"] for s, _ in parsed] == ["D-0001-2024"] and skipped == 1
    assert "D-0002-2024" in caplog.text and "2024-13-45" in caplog.text


def test_malformed_record_is_skipped_and_logged(caplog):
    import seed
    from fake_fda import record
    broken = {**record(2), "product_description": None}       # .split on None fails
    with caplog.at_level("WARNING", logger="seed"):
        parsed, skipped = seed.parse_records([record(1), broken], ["kembly"])
    assert len(parsed) == 1 and skipped == 1
    assert "D-0002-2024" in caplog.text
