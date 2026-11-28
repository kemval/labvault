"""Query shape and page speed at scale (audit M1, roadmap 4.2, ADR 0020)."""
import sqlite3

import pytest

import db
from repo import core, results, samples
from test_app_login import go, login, no_network, run_app  # noqa: F401
from test_tracking_page import bulk_samples


def bulk_results(sample_count, status="Pass"):
    """One result on each of S-00000 … (sample_count - 1)."""
    with core.transaction() as conn:
        conn.executemany(
            "INSERT INTO test_results (sample_id, test_name, result_value, result_unit, "
            "spec_min, spec_max, status, tested_by, tested_at, notes) "
            "VALUES (?, 'pH', 6.0, 'pH', 4.5, 7.5, ?, 'kembly', '2026-01-02', '')",
            [(f"S-{i:05d}", status) for i in range(sample_count)])
    db.clear_data_caches()


@pytest.fixture
def count_queries(monkeypatch):
    """Counts the SELECT statements every new connection runs."""
    seen = []
    connect = sqlite3.connect

    def counting(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(
            lambda sql: seen.append(sql) if sql.lstrip().upper().startswith("SELECT") else None)
        return conn
    monkeypatch.setattr(core.sqlite3, "connect", counting)
    return seen


def results_page_queries(at, count_queries):
    db.clear_data_caches()
    count_queries.clear()
    at.run()
    return len(count_queries)


def test_results_page_runs_the_same_queries_for_10_or_300_samples(lab_db, settings,
                                                                    count_queries):
    # Before 4.2 the "View All Results" tab ran one query per sample (M1).
    settings(demo="true")
    at = go(login(run_app(), "admin", "admin123"), "Test Results")
    bulk_samples(10)
    bulk_results(10)
    few = results_page_queries(at, count_queries)
    with core.transaction() as conn:
        conn.execute("DELETE FROM test_results")
        conn.execute("DELETE FROM samples")
    bulk_samples(300)
    bulk_results(300)
    many = results_page_queries(at, count_queries)
    assert 0 < few == many, (few, many)


def test_find_results_pages_and_filters(lab_db):
    bulk_samples(150)
    bulk_results(150)
    with core.transaction() as conn:
        conn.execute("UPDATE test_results SET status = 'Fail (OOS)' WHERE id <= 7")
    page, total = results.find_results(limit=100, offset=100)
    assert (len(page), total) == (50, 150)
    assert page[0]["id"] > page[-1]["id"]                         # newest first
    assert {"product_name", "sample_status", "review"} <= page[0].keys()
    oos, total = results.find_results("Fail (OOS)")
    assert total == len(oos) == 7


def test_results_tab_shows_one_page_at_a_time(lab_db, settings):
    bulk_samples(150)
    bulk_results(150)
    settings(demo="true")
    at = go(login(run_app(), "admin", "admin123"), "Test Results")
    assert len(at.dataframe[0].value) == 100
    at.number_input(key="results_page").set_value(2).run()
    assert len(at.dataframe[0].value) == 50
    assert any("101–150" in c.value for c in at.caption)


def test_loggable_samples_are_selected_in_sql(lab_db):
    bulk_samples(6, lambda i: {"status": "In Progress" if i < 4 else "Pending",
                               "assigned_to": "kembly" if i % 2 else "carlos"})
    assert [s["sample_id"] for s in samples.loggable_samples("kembly")] == ["S-00003",
                                                                            "S-00001"]
    assert len(samples.loggable_samples()) == 4                  # admins: every In Progress


def test_report_filters_follow_the_multiselects(lab_db):
    bulk_samples(4, lambda i: {"priority": ["Critical", "Major"][i % 2]})
    assert len(samples.report_samples(None, ["Critical"])) == 2
    assert samples.report_samples([], None) == []                  # nothing selected
    assert samples.count_by_source() == {"Manual": 4}


def test_benchmark_runs_every_page_within_budget(tmp_path, monkeypatch):
    import services
    from scripts import benchmark
    monkeypatch.setenv("LABVAULT_DEMO_MODE", "true")
    monkeypatch.setattr(services, "import_fda", services.import_fda)   # restored after
    counts = benchmark.build(str(tmp_path / "bench.db"), 300)
    assert counts["samples"] == 300 and counts["oos_investigations"] > 0
    timings = benchmark.time_pages()
    assert {"Test Results", "Reports", "Admin"} <= timings.keys()
    assert max(timings.values()) < 5                               # generous: CI machines vary
