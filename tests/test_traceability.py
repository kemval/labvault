"""Requirements traceability (roadmap 5.5, ADR 0027)."""
from scripts import traceability as t


def test_every_requirement_is_traced_and_the_documents_are_current(capsys):
    assert t.main(["--check"]) == 0, capsys.readouterr().err


def test_problems_are_reported():
    good = {"id": "X-01", "area": "A", "title": "T", "regulation": [], "impact": "H",
            "likelihood": "M", "detection": "L", "controls": "C", "adrs": ["0001"],
            "tests": ["test_a.py::test_x"]}
    tests, adrs = {"test_a.py::test_x"}, {"0001": "0001-a.md"}
    assert t.problems([good], tests, adrs) == []
    found = t.problems([{**good, "tests": []}, {**good, "impact": "X"},
                        {**good, "tests": ["test_a.py::test_gone"], "adrs": ["0999"]},
                        {k: v for k, v in good.items() if k != "controls"}], tests, adrs)
    assert found == ["X-01: no test traces this requirement",
                     "X-01: duplicate id", "X-01: impact must be H, M or L",
                     "X-01: duplicate id", "X-01: test not found: test_a.py::test_gone",
                     "X-01: ADR not found: 0999",
                     "X-01: missing 'controls'", "X-01: duplicate id"]


def test_gamp_risk_priority():
    assert t.risk({"impact": "H", "likelihood": "M", "detection": "L"}) == (1, "High")
    assert t.risk({"impact": "M", "likelihood": "M", "detection": "H"}) == (2, "Low")
    assert t.risk({"impact": "L", "likelihood": "L", "detection": "L"}) == (3, "Medium")


def test_existing_tests_sees_this_file():
    assert "test_traceability.py::test_gamp_risk_priority" in t.existing_tests()
