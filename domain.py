"""
domain.py — LabVault's domain vocabulary, defined once (audit TD1).

These strings are stored in the database, so changing or adding one needs
a migration: the database CHECK constraints (migration 3) hold a frozen
copy, and tests/test_domain.py fails if the two drift apart.
No imports from the rest of the app — every layer may use this module.
"""

import re

# Samples
STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_REJECTED = (
    "Pending", "In Progress", "Completed", "Rejected")
SAMPLE_STATUSES = (STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_REJECTED)

PRIORITY_CRITICAL, PRIORITY_MAJOR, PRIORITY_MINOR = "Critical", "Major", "Minor"
PRIORITIES = (PRIORITY_CRITICAL, PRIORITY_MAJOR, PRIORITY_MINOR)

RECALL_CLASSES = ("Class I", "Class II", "Class III")

# Dosage forms a sample can have. Protocols may also target "Non-sterile"
# products as a group (e.g. the microbial-limits protocol).
SAMPLE_TYPES = ("Tablet", "Capsule", "Injectable", "Liquid", "Topical", "Powder")
PROTOCOL_SAMPLE_TYPES = SAMPLE_TYPES + ("Non-sterile",)

SOURCE_FDA, SOURCE_MANUAL = "FDA", "Manual"
SOURCES = (SOURCE_FDA, SOURCE_MANUAL)

# Test results
RESULT_PASS, RESULT_OOS = "Pass", "Fail (OOS)"   # OOS = out of specification
RESULT_STATUSES = (RESULT_PASS, RESULT_OOS)

# Accounts
ROLE_ADMIN, ROLE_LAB_TECH, ROLE_SYSTEM = "admin", "lab_tech", "system"
ROLES = (ROLE_ADMIN, ROLE_LAB_TECH, ROLE_SYSTEM)

# Non-login accounts that own automated work (role ROLE_SYSTEM).
SYSTEM_USER = "system"         # migrations, default data, unattended imports
SIMULATOR_USER = "simulator"   # simulated test results
SYSTEM_ACCOUNTS = (SYSTEM_USER, SIMULATOR_USER)


# ─────────────────────────────────────────────
# SAMPLE LIFECYCLE AND PERMISSIONS (audit H5, ADR 0011)
# Pure rules shared by services.py (which enforces them) and the views
# (which offer only what they allow). `user` is {"username", "role"};
# `sample` needs status, assigned_to and, for completion, approved_count and
# unreviewed_count (repo.samples.REVIEW_COUNTS).
# ─────────────────────────────────────────────

TRANSITIONS = {
    STATUS_PENDING:     (STATUS_IN_PROGRESS, STATUS_REJECTED),
    STATUS_IN_PROGRESS: (STATUS_COMPLETED, STATUS_REJECTED),
    STATUS_COMPLETED:   (STATUS_IN_PROGRESS,),   # reopen — admin only
    STATUS_REJECTED:    (STATUS_PENDING,),       # reopen — admin only
}
TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_REJECTED)
REOPENINGS = {(STATUS_COMPLETED, STATUS_IN_PROGRESS), (STATUS_REJECTED, STATUS_PENDING)}


def is_admin(user) -> bool:
    return user["role"] == ROLE_ADMIN


def may_edit(user, sample) -> bool:
    """Admins edit any sample; a lab tech edits samples assigned to them,
    and may claim an unassigned one."""
    if is_admin(user):
        return True
    return user["role"] == ROLE_LAB_TECH and sample["assigned_to"] in (None, user["username"])


def status_options(user, sample) -> list:
    """Statuses `user` may choose for `sample`; the current one is first."""
    current = sample["status"]
    if not may_edit(user, sample):
        return [current]
    return [current] + [s for s in TRANSITIONS[current]
                        if transition_error(user, sample, s) is None]


def assignee_options(user, sample, techs) -> list:
    """Assignees `user` may choose (None = unassigned); the current one first."""
    current = sample["assigned_to"]
    if not may_edit(user, sample) or sample["status"] in TERMINAL_STATUSES:
        return [current]
    if is_admin(user):
        return [current] + [t for t in [None, *techs] if t != current]
    if current is None:                       # a tech may claim it — nothing else
        return [None, user["username"]]
    return [current]


def transition_error(user, sample, new_status):
    """Why `user` may not move `sample` to `new_status`, or None if allowed."""
    current = sample["status"]
    if new_status == current:
        return None
    if new_status not in TRANSITIONS.get(current, ()):
        return f"A {current} sample can't be moved to {new_status}."
    if (current, new_status) in REOPENINGS and not is_admin(user):
        return f"Only an admin can reopen a {current} sample."
    if new_status == STATUS_COMPLETED:
        # Only reviewed results count toward the sample (ADR 0014).
        if sample.get("unreviewed_count"):
            return (f"{sample['unreviewed_count']} result(s) still awaiting review. "
                    "Each result needs a second person's signature before completion.")
        if not sample.get("approved_count"):
            return "Completing a sample needs at least one approved test result."
    return None


def change_error(user, sample, new_status, new_assignee, assignee_role=None):
    """
    Why `user` may not make this change, or None. `assignee_role` is the
    role of `new_assignee` (None when unassigning). Claiming an unassigned
    sample and starting it can happen in one change.
    """
    if not may_edit(user, sample):
        return (f"Only {sample['assigned_to']} (the assignee) or an admin can change "
                f"sample {sample['sample_id']}.")
    if new_assignee != sample["assigned_to"]:
        if sample["status"] in TERMINAL_STATUSES and new_status == sample["status"]:
            return f"A {sample['status']} sample can't be reassigned."
        if not is_admin(user) and not (sample["assigned_to"] is None
                                       and new_assignee == user["username"]):
            return "Only an admin can reassign a sample to someone else."
        if new_assignee is not None and assignee_role != ROLE_LAB_TECH:
            return (f"Samples can only be assigned to active lab techs; "
                    f"{new_assignee} isn't one.")
    return transition_error(user, sample, new_status)


def result_entry_error(user, sample):
    """Why `user` may not log a result against `sample`, or None."""
    if sample["status"] != STATUS_IN_PROGRESS:
        return (f"Results can only be logged while a sample is {STATUS_IN_PROGRESS} "
                f"(this one is {sample['status']}).")
    if not (is_admin(user) or sample["assigned_to"] == user["username"]):
        return "Only the assigned lab tech or an admin can log results for this sample."
    return None


# ─────────────────────────────────────────────
# TESTS, SPECIFICATIONS AND RESULT EVALUATION (audit H4, ADR 0012)
# ─────────────────────────────────────────────

TEST_TYPES = (
    "Potency (% Label Claim)", "Dissolution (60 min)", "pH",
    "Sterility / Microbial Count", "Visible Particulates", "Water Content (%)",
    "Hardness (N)", "Friability (%)", "Disintegration Time (min)",
    "Label Review", "Other",
)
# Judged pass/fail by the analyst; no numeric value and no specification.
QUALITATIVE_TESTS = ("Label Review", "Other")
# Tests that are measured against a specification (sample type × test).
QUANTITATIVE_TESTS = tuple(t for t in TEST_TYPES if t not in QUALITATIVE_TESTS)
UNITS = ("%", "pH", "CFU/mL", "CFU/g", "particles/container", "N", "min", "mg", "other")
OUTCOME_FAIL = "Fail"
OUTCOMES = (RESULT_PASS, OUTCOME_FAIL)    # qualitative outcomes the analyst chooses


def spec_error(spec_min, spec_max):
    """Why these limits can't form a specification, or None."""
    if spec_min is None and spec_max is None:
        return "Set at least one limit (minimum, maximum or both)."
    if spec_min is not None and spec_max is not None and spec_min > spec_max:
        return f"Minimum ({spec_min}) can't be greater than maximum ({spec_max})."
    return None


def determine_status(value, spec_min, spec_max):
    """Pass, or OOS when the value is outside the limits. None means no limit."""
    if spec_min is not None and value < spec_min:
        return RESULT_OOS
    if spec_max is not None and value > spec_max:
        return RESULT_OOS
    return RESULT_PASS


def evaluate_result(test_name, value, outcome, spec):
    """
    Validate an entry and decide its status: (status, errors).
    A quantitative test needs a value and a specification (a dict with
    spec_min/spec_max, or None when the lab hasn't defined one); a
    qualitative test needs an outcome and no value. 0 is a real value.
    """
    if test_name not in TEST_TYPES:
        return None, [f"Unknown test: {test_name}."]
    if test_name in QUALITATIVE_TESTS:
        errors = []
        if outcome not in OUTCOMES:
            errors.append(f"{test_name} is a pass/fail test — choose an outcome.")
        if value is not None:
            errors.append(f"{test_name} is a pass/fail test — leave Result Value blank.")
        if errors:
            return None, errors
        return (RESULT_PASS if outcome == RESULT_PASS else RESULT_OOS), []

    errors = []
    if spec is None:
        errors.append(f"No specification is defined for {test_name} on this sample type. "
                      "Ask an admin to add one on the Specifications page.")
    if value is None:
        errors.append("Enter a Result Value — this test is measured against its specification.")
    if outcome is not None:
        errors.append(f"{test_name} is a numeric test — leave the outcome blank.")
    if errors:
        return None, errors
    return determine_status(value, spec["spec_min"], spec["spec_max"]), []


# ─────────────────────────────────────────────
# SIGN-IN POLICY (audit H6, ADR 0013)
# ─────────────────────────────────────────────

MAX_FAILED_LOGINS = 5        # consecutive failures before the account is locked
LOCKOUT_MINUTES = 15
SESSION_IDLE_MINUTES = 30    # idle time after which the next action signs the user out


# ─────────────────────────────────────────────
# ACCOUNT MANAGEMENT (audit 3.6, ADR 0017)
# ─────────────────────────────────────────────

MIN_PASSWORD_LENGTH = 12
LOGIN_ROLES = (ROLE_ADMIN, ROLE_LAB_TECH)          # roles an admin can give an account
_USERNAME = re.compile(r"[a-z][a-z0-9._-]{2,31}")


def username_error(username):
    if not _USERNAME.fullmatch(username or ""):
        return ("Usernames are 3–32 characters: lowercase letters, digits, '.', '_' or '-', "
                "starting with a letter.")
    return None


def password_error(password, username):
    """Why `password` can't be set for `username`, or None."""
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return f"Passwords must be at least {MIN_PASSWORD_LENGTH} characters."
    if password.strip().lower() == (username or "").lower():
        return "The password can't be the username."
    return None


def account_change_error(actor, target):
    """
    Why `actor` may not manage `target` (an account dict, or None), or None.
    Admins manage other login accounts — never their own, so the acting
    admin always stays an active admin and at least one remains.
    """
    if not is_admin(actor):
        return "Only an admin can manage accounts."
    if target is None:
        return "That account doesn't exist."
    if target["username"] == actor["username"]:
        return "You can't change your own account here; ask another admin."
    return None


# ─────────────────────────────────────────────
# RESULT REVIEW AND E-SIGNATURE (audit 3.3, ADR 0014)
# ─────────────────────────────────────────────

REVIEW_APPROVED = "Approved"
REVIEW_REJECTED = "Rejected"
REVIEW_MEANINGS = (REVIEW_APPROVED, REVIEW_REJECTED)
REVIEW_AWAITING = "Awaiting review"
# The meaning of each signature as shown to the signer and on the record (Part 11 §11.50).
SIGNATURE_MEANING_TEXT = {
    REVIEW_APPROVED: "Reviewed and approved — the result is valid and counts toward the sample",
    REVIEW_REJECTED: "Reviewed and rejected — the result is invalid; a retest is needed",
}


def review_error(user, result, meaning=None):
    """
    Why `user` may not sign `result` (with `meaning`, when given), or None.
    `result` needs tested_by, review (its signature meaning, or None),
    sample_status, status and the investigation fields (allowed_meanings).
    Second-person rule: anyone may review except the analyst who logged it.
    """
    if result.get("review"):
        return f"This result was already signed ({result['review']})."
    if result["tested_by"] == user["username"]:
        return "You logged this result, so someone else has to review it."
    if result["sample_status"] != STATUS_IN_PROGRESS:
        return "Results can only be reviewed while the sample is In Progress."
    allowed = allowed_meanings(result)
    if not allowed:
        return ("This OOS result has an open investigation. It can be signed once an admin "
                "closes the investigation.")
    if meaning is not None and meaning not in allowed:
        return (f"The investigation concluded “{result['conclusion']}”, so this result "
                f"can only be signed as {allowed[0]}.")
    return None


# ─────────────────────────────────────────────
# OOS INVESTIGATIONS (audit 3.4, ADR 0015)
# ─────────────────────────────────────────────

INVESTIGATION_OPEN = "Open"
INVESTIGATION_CLOSED = "Closed"
CONCLUSION_LAB_ERROR = "Assignable laboratory error"
CONCLUSION_CONFIRMED = "OOS confirmed"
CONCLUSIONS = (CONCLUSION_LAB_ERROR, CONCLUSION_CONFIRMED)
CONCLUSION_TEXT = {
    CONCLUSION_LAB_ERROR: "Assignable laboratory error — the result is invalid; it can only "
                          "be rejected, and the sample retested",
    CONCLUSION_CONFIRMED: "OOS confirmed — no laboratory error found; the result is valid "
                          "and can only be approved",
}
# How a closed investigation's conclusion decides the result's signature.
CONCLUSION_MEANING = {CONCLUSION_LAB_ERROR: REVIEW_REJECTED,
                      CONCLUSION_CONFIRMED: REVIEW_APPROVED}


def allowed_meanings(result):
    """
    The signature meanings `result` may receive. An OOS result can't be
    signed until its investigation is closed, and then only as its
    conclusion dictates — so a failure can't be invalidated without QA
    finding a laboratory error. `result` needs status and, for OOS,
    investigation_status and conclusion.
    """
    if result["status"] != RESULT_OOS:
        return REVIEW_MEANINGS
    if result.get("investigation_status") != INVESTIGATION_CLOSED:
        return ()
    return (CONCLUSION_MEANING[result["conclusion"]],)


def investigation_error(user, investigation):
    """Why `user` may not close `investigation` (needs status and the
    result's tested_by), or None. Admins act as QA, never on their own result."""
    if not is_admin(user):
        return "Only an admin (QA) can close an OOS investigation."
    if investigation["status"] != INVESTIGATION_OPEN:
        return "This investigation is already closed."
    if investigation["tested_by"] == user["username"]:
        return "You logged this result, so another admin has to close its investigation."
    return None
