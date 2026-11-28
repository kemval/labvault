"""Result entry can't produce false passes (audit H4) and uses QA's specs (ADR 0012)."""
import pytest

import services
from domain import evaluate_result
from test_app_login import login, run_app, no_network  # noqa: F401
from test_services import audit, rows

FAIL = "Fail (OOS)"


def spec(lo, hi):
    return {"spec_min": lo, "spec_max": hi}


# ── evaluate_result: the rules ──────────────────────────────────────────────

@pytest.mark.parametrize("value,lo,hi,expected", [
    (0.0, 0.0, 0.0, "Pass"),       # sterility: 0 CFU with spec max 0
    (1.0, 0.0, 0.0, FAIL),
    (0.0, None, 10.0, "Pass"),     # 0 is a real value, not "missing"
    (-0.5, -1.0, 0.0, "Pass"),     # negative limits
    (-1.5, -1.0, 0.0, FAIL),
    (80.0, 80.0, None, "Pass"),    # exactly on the limit passes
    (79.9, 80.0, None, FAIL),
    (110.1, None, 110.0, FAIL),
])
def test_quantitative_results_are_evaluated_against_the_spec(value, lo, hi, expected):
    assert evaluate_result("Potency (% Label Claim)", value, None, spec(lo, hi)) == (expected, [])


def test_quantitative_result_requires_a_value():
    status, errors = evaluate_result("pH", None, None, spec(4.5, 7.5))
    assert status is None and any("Result Value" in e for e in errors)


def test_quantitative_result_requires_a_specification():
    status, errors = evaluate_result("pH", 6.0, None, None)
    assert status is None and any("No specification" in e for e in errors)


def test_quantitative_test_rejects_an_outcome():
    status, errors = evaluate_result("pH", 6.0, "Pass", spec(4.5, 7.5))
    assert status is None and errors


@pytest.mark.parametrize("test", ["Label Review", "Other"])
@pytest.mark.parametrize("outcome, expected", [("Pass", "Pass"), ("Fail", FAIL)])
def test_qualitative_tests_use_the_recorded_outcome(test, outcome, expected):
    assert evaluate_result(test, None, outcome, None) == (expected, [])


@pytest.mark.parametrize("value, outcome", [(None, None), (5.0, "Pass")])
def test_qualitative_test_needs_an_outcome_and_no_value(value, outcome):
    status, errors = evaluate_result("Label Review", value, outcome, None)
    assert status is None and errors


def test_unknown_test_is_rejected():
    assert evaluate_result("Smell", 1.0, None, spec(0, 1))[0] is None


# ── the service decides, using the current spec ──────────────────────────────

def log(sid, test, value=None, outcome=None, user="kembly", **extra):
    return services.record_result({"sample_id": sid, "test_name": test, "result_value": value,
                                   "outcome": outcome, "tested_at": "2026-01-02", "notes": "",
                                   **extra}, user)


def test_service_stores_the_spec_it_judged_against(open_sample):
    saved = log(open_sample, "Sterility / Microbial Count", 3.0)
    [r] = rows("SELECT * FROM test_results")
    assert (r["result_value"], r["spec_min"], r["spec_max"], r["result_unit"], r["status"]) == \
        (3.0, 0.0, 0.0, "CFU/mL", FAIL)
    assert (r["spec_id"], r["spec_version"]) == (saved["spec"]["id"], 1)
    assert "spec v1: 0 to 0 CFU/mL" in audit("RESULT_LOGGED")[0]["detail"]


def test_limits_sent_by_the_caller_are_ignored(open_sample):
    # An analyst (or a tampered page) can't widen the limits to pass.
    log(open_sample, "Sterility / Microbial Count", 3.0, spec_min=0.0, spec_max=100.0)
    assert rows("SELECT spec_max, status FROM test_results") == [{"spec_max": 0.0, "status": FAIL}]


def test_numeric_result_without_spec_is_blocked(open_sample):
    with pytest.raises(services.ServiceError, match="No specification"):
        log(open_sample, "Hardness (N)", 50.0)            # no default spec for this
    assert rows("SELECT * FROM test_results") == []


def test_spec_change_applies_to_new_results_only(open_sample):
    log(open_sample, "pH", 7.0)                                       # v1: 4.5–7.5 → Pass
    services.save_specification("Injectable", "pH", 4.5, 6.5, "pH", "admin",
                                reason="Tightened per QA review", expected_version=1)
    log(open_sample, "pH", 7.0)                                       # v2: 4.5–6.5 → OOS
    assert [(r["status"], r["spec_max"], r["spec_version"])
            for r in rows("SELECT * FROM test_results ORDER BY id")] == \
        [("Pass", 7.5, 1), (FAIL, 6.5, 2)]


# ── the real form ───────────────────────────────────────────────────────────

@pytest.fixture
def results_page(open_sample, settings):
    settings(demo="true")
    at = login(run_app(), "kembly", "lab2024")
    at.sidebar.radio[0].set_value("📋  Test Results").run()
    assert not at.exception, at.exception
    return at


def widget(widgets, label):
    return next(w for w in widgets if w.label.startswith(label))


def choose(at, test):
    at.selectbox(key="result_test").set_value(test).run()
    assert not at.exception, at.exception
    return at


def test_form_shows_the_spec_and_offers_no_limit_inputs(results_page):
    at = choose(results_page, "Sterility / Microbial Count")
    assert any("Specification v1" in i.value and "0 to 0 CFU/mL" in i.value for i in at.info)
    assert not [w for w in at.number_input if "Spec" in w.label]


def test_form_flags_contamination_against_a_zero_limit(results_page):
    at = choose(results_page, "Sterility / Microbial Count")
    widget(at.number_input, "Result Value").set_value(3.0)
    widget(at.button, "Submit Result").click().run()
    assert rows("SELECT status FROM test_results") == [{"status": FAIL}]
    assert any("OOS RESULT" in e.value for e in at.error)


def test_form_stores_qualitative_fail(results_page):
    at = choose(results_page, "Label Review")
    widget(at.selectbox, "Outcome").set_value("Fail")
    widget(at.button, "Submit Result").click().run()
    assert rows("SELECT status, result_value FROM test_results") == [
        {"status": FAIL, "result_value": None}]


def test_form_rejects_missing_value_and_stores_nothing(results_page):
    at = choose(results_page, "pH")
    widget(at.button, "Submit Result").click().run()
    assert rows("SELECT * FROM test_results") == []
    assert any("Result Value" in e.value for e in at.error)


def test_form_blocks_tests_without_a_spec(results_page):
    at = choose(results_page, "Hardness (N)")
    assert any("No specification is defined" in w.value for w in at.warning)
    assert not [b for b in at.button if b.label == "Submit Result"]
