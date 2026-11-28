"""Second-person review with e-signature (audit 3.3, migration 7, ADR 0014)."""
import sqlite3

import pytest

import services
from domain import MAX_FAILED_LOGINS
from repo import core
from test_app_login import login, run_app
from test_result_entry import log
from test_services import audit, rows

FAIL = "Fail (OOS)"


def sign(result_id, user="carlos", password="lab2024", meaning="Approved", reason=""):
    return services.sign_result(result_id, user, password, meaning, reason)


def update(sid, user="kembly", **change):
    version = rows("SELECT version FROM samples WHERE sample_id = ?", (sid,))[0]["version"]
    return services.update_sample(sid, version, user, reason="test", **change)


def sql(statement, params=()):
    with core.transaction() as conn:
        conn.execute(statement, params)


@pytest.fixture
def result(open_sample):
    """kembly's Pass result on kembly's In Progress Injectable."""
    return log(open_sample, "Potency (% Label Claim)", 100.0)["id"]


# ── signing ──────────────────────────────────────────────────

def test_approval_is_recorded_with_meaning_signer_and_audit(result):
    saved = sign(result)
    [sig] = rows("SELECT * FROM result_signatures")
    assert (sig["result_id"], sig["signed_by"], sig["meaning"], sig["signed_at"]) == \
        (result, "carlos", "Approved", saved["signed_at"])
    [entry] = audit("RESULT_APPROVED")
    assert (entry["user"], entry["old_value"], entry["new_value"]) == \
        ("carlos", "Awaiting review", "Approved")
    assert "Reviewed and approved" in entry["detail"] and "by kembly" in entry["detail"]


@pytest.mark.parametrize("signer, password", [("admin", "admin123"), ("maria", "lab2024")])
def test_anyone_but_the_analyst_may_sign(result, signer, password):
    assert sign(result, signer, password)["meaning"] == "Approved"


def test_analyst_cannot_sign_own_result(result):
    with pytest.raises(services.PermissionDeniedError, match="someone else"):
        sign(result, "kembly")
    assert rows("SELECT * FROM result_signatures") == []


def test_database_also_refuses_self_signature(result):
    with pytest.raises(sqlite3.IntegrityError, match="other than its analyst"):
        sql("INSERT INTO result_signatures (result_id, signed_by, meaning) "
            "VALUES (?, 'kembly', 'Approved')", (result,))


def test_system_accounts_cannot_sign(result):
    with pytest.raises(services.PermissionDeniedError):
        sign(result, "system", "!")


def test_signatures_are_permanent(result):
    sign(result)
    with pytest.raises(services.PermissionDeniedError, match="already signed"):
        sign(result, "maria")
    for statement in ("UPDATE result_signatures SET meaning = 'Rejected'",
                      "DELETE FROM result_signatures"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            sql(statement)


def test_rejection_needs_a_reason(result):
    with pytest.raises(services.ServiceError, match="reason"):
        sign(result, meaning="Rejected", reason="  ")
    with pytest.raises(sqlite3.IntegrityError):         # and the database agrees
        sql("INSERT INTO result_signatures (result_id, signed_by, meaning) "
            "VALUES (?, 'carlos', 'Rejected')", (result,))
    sign(result, meaning="Rejected", reason="Wrong reference standard lot")
    assert audit("RESULT_REJECTED")[0]["reason"] == "Wrong reference standard lot"


def test_unknown_meaning_is_refused(result):
    with pytest.raises(services.ServiceError, match="meaning"):
        sign(result, meaning="Looks fine")


def test_only_results_on_in_progress_samples_can_be_signed(open_sample, result):
    update(open_sample, "admin", status="Rejected")
    with pytest.raises(services.PermissionDeniedError, match="In Progress"):
        sign(result)


# ── the password check ───────────────────────────────────────

def test_wrong_password_signs_nothing_and_is_audited(result):
    with pytest.raises(services.SignatureError):
        sign(result, password="wrong")
    assert rows("SELECT * FROM result_signatures") == []
    [failed] = audit("SIGNATURE_FAILED")
    assert failed["user"] == "carlos" and "1 of" in failed["detail"]


def test_wrong_signature_passwords_count_toward_lockout(result):
    for _ in range(MAX_FAILED_LOGINS):
        with pytest.raises(services.SignatureError):
            sign(result, password="wrong")
    assert audit("ACCOUNT_LOCKED")[0]["user"] == "carlos"
    with pytest.raises(services.SignatureError):        # right password, but locked
        sign(result)
    assert services.sign_in("carlos", "lab2024") is None


# ── effect on the sample ─────────────────────────────────────

def test_rejected_result_does_not_count_and_a_retest_is_needed(open_sample):
    oos = log(open_sample, "Potency (% Label Claim)", 80.0)["id"]
    sign(oos, meaning="Rejected", reason="Sample prep error, documented in notebook p. 12")
    with pytest.raises(services.PermissionDeniedError, match="at least one approved"):
        update(open_sample, status="Completed")
    retest = log(open_sample, "Potency (% Label Claim)", 99.0)["id"]
    sign(retest)
    assert update(open_sample, status="Completed")
    # The rejected OOS stays on record and in the OOS counts (ADR 0014).
    assert rows("SELECT COUNT(*) AS n FROM test_results WHERE status = ?", (FAIL,))[0]["n"] == 1


# ── the page ─────────────────────────────────────────────────

def open_review(username, password):
    at = login(run_app(), username, password)
    at.sidebar.radio[0].set_value("📋  Test Results").run()
    assert not at.exception, at.exception
    return at


def fill(at, meaning, password, reason=""):
    next(r for r in at.radio if r.label.startswith("Meaning")).set_value(meaning)
    next(w for w in at.text_input if w.label.startswith("Reason")).input(reason)
    next(w for w in at.text_input if w.label.startswith("Your password")).input(password)
    next(b for b in at.button if b.label == "Sign").click().run()
    assert not at.exception, at.exception
    return at


def test_reviewer_signs_on_the_page(result, settings):
    settings(demo="true")
    at = fill(open_review("carlos", "lab2024"), "Approved", "lab2024")
    assert rows("SELECT signed_by, meaning FROM result_signatures") == [
        {"signed_by": "carlos", "meaning": "Approved"}]
    assert any(f"Signed result #{result}: Approved" in s.value for s in at.success)


def test_wrong_password_on_the_page_shows_an_error(result, settings):
    settings(demo="true")
    at = fill(open_review("carlos", "lab2024"), "Approved", "nope")
    assert any("Signature refused" in e.value for e in at.error)
    assert rows("SELECT * FROM result_signatures") == []


def test_analyst_sees_no_own_results_to_review(result, settings):
    settings(demo="true")
    at = open_review("kembly", "lab2024")
    assert not [b for b in at.button if b.label == "Sign"]
    assert any("you logged are awaiting" in c.value for c in at.caption)
