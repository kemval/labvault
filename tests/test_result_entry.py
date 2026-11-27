"""Result entry can't produce false passes (audit H4)."""
import pytest

from test_app_login import login, run_app, no_network  # noqa: F401
from views.test_results import evaluate_result

FAIL = "Fail (OOS)"


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
def test_quantitative_results_are_evaluated_against_limits(value, lo, hi, expected):
    status, errors = evaluate_result("Potency (% Label Claim)", value, lo, hi, None)
    assert errors == [] and status == expected


def test_quantitative_result_requires_a_value():
    status, errors = evaluate_result("pH", None, 4.5, 7.5, None)
    assert status is None and any("Result Value" in e for e in errors)


def test_quantitative_result_requires_at_least_one_limit():
    status, errors = evaluate_result("pH", 6.0, None, None, None)
    assert status is None and any("limit" in e for e in errors)


def test_min_above_max_is_rejected():
    status, errors = evaluate_result("pH", 6.0, 7.5, 4.5, None)
    assert status is None and any("Minimum" in e for e in errors)


def test_quantitative_test_rejects_qualitative_outcome():
    status, errors = evaluate_result("pH", 6.0, 4.5, 7.5, "Pass")
    assert status is None and errors


@pytest.mark.parametrize("outcome,expected", [("Pass", "Pass"), ("Fail", FAIL)])
def test_qualitative_test_uses_the_recorded_outcome(outcome, expected):
    status, errors = evaluate_result("Label Review", None, None, None, outcome)
    assert errors == [] and status == expected


def test_qualitative_test_requires_an_outcome():
    status, errors = evaluate_result("Label Review", None, None, None, None)
    assert status is None and any("Outcome" in e for e in errors)


def test_qualitative_test_rejects_numbers():
    status, errors = evaluate_result("Label Review", 5.0, None, None, "Pass")
    assert status is None and errors


def test_other_accepts_either_a_value_or_an_outcome_but_not_both():
    assert evaluate_result("Other", 5.0, 0.0, 10.0, None) == ("Pass", [])
    assert evaluate_result("Other", None, None, None, "Fail") == (FAIL, [])
    status, errors = evaluate_result("Other", 5.0, 0.0, 10.0, "Fail")
    assert status is None and errors


# ── the real form ───────────────────────────────────────────────────────────

@pytest.fixture
def results_page(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    fresh_db.insert_sample({
        "sample_id": "S-1", "product_name": "Ceftriaxone Injection", "lot_number": "",
        "manufacturer": "M", "sample_type": "Injectable", "recall_class": "Class I",
        "priority": "Critical", "reason_for_recall": "", "collection_date": "2026-01-01",
        "status": "In Progress", "assigned_to": "kembly", "protocol_id": None,
        "notes": "", "source": "Manual",
    })
    at = login(run_app(), "kembly", "lab2024")
    at.sidebar.radio[0].set_value("📋  Test Results").run()
    assert not at.exception, at.exception
    return at


def widget(widgets, label):
    return next(w for w in widgets if w.label == label)


def submit(at, test, value=None, lo=None, hi=None, outcome="—", unit="%"):
    widget(at.selectbox, "Test Name *").set_value(test)
    widget(at.selectbox, "Unit").set_value(unit)
    widget(at.selectbox, "Qualitative Outcome").set_value(outcome)
    widget(at.number_input, "Result Value").set_value(value)
    widget(at.number_input, "Spec Minimum").set_value(lo)
    widget(at.number_input, "Spec Maximum").set_value(hi)
    widget(at.button, "Submit Result").click().run()
    assert not at.exception, at.exception
    return at


def test_form_stores_zero_limit_and_flags_contamination(results_page, fresh_db):
    at = submit(results_page, "Sterility / Microbial Count", value=3.0, lo=0.0, hi=0.0,
                unit="CFU/mL")
    fresh_db.get_results_for_sample.clear()
    [r] = fresh_db.get_results_for_sample("S-1")
    assert (r["result_value"], r["spec_min"], r["spec_max"], r["status"]) == (3.0, 0.0, 0.0, "Fail (OOS)")
    assert any("OOS RESULT" in e.value for e in at.error)


def test_form_stores_qualitative_fail(results_page, fresh_db):
    submit(results_page, "Label Review", outcome="Fail", unit="N/A")
    fresh_db.get_results_for_sample.clear()
    [r] = fresh_db.get_results_for_sample("S-1")
    assert r["status"] == "Fail (OOS)" and r["result_value"] is None


def test_form_rejects_missing_value_and_stores_nothing(results_page, fresh_db):
    at = submit(results_page, "pH", value=None, lo=4.5, hi=7.5, unit="pH")
    fresh_db.get_results_for_sample.clear()
    assert fresh_db.get_results_for_sample("S-1") == []
    assert any("Result Value" in e.value for e in at.error)
