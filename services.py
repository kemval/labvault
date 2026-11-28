"""
services.py — LabVault use cases.

Every function that changes data runs in ONE transaction that also writes
its audit row, so a change can never be saved without its audit entry (or
the reverse). Caches are cleared only after a successful commit.
Views call these functions; they never write to the database directly.
See docs/adr/0005-service-layer.md.
"""

import uuid

import db  # cache invalidation only
import domain
from domain import ROLE_SYSTEM, SOURCE_MANUAL, STATUS_PENDING, SYSTEM_USER
import seed
from repo import (audit, core, fda_import, passwords, protocols, results, samples,
                  investigations, signatures, specifications, users)


class ServiceError(Exception):
    """A business-rule failure the UI should show to the user."""


class NotFoundError(ServiceError):
    pass


class ConcurrentUpdateError(ServiceError):
    """The record changed since the caller read it; reload and retry."""


class PermissionDeniedError(ServiceError):
    """The user's role or assignment doesn't allow this action (ADR 0011)."""


def _actor(conn, username: str) -> dict:
    """The acting user as stored — the role comes from the database, never the caller."""
    row = conn.execute("SELECT username, role, active FROM users WHERE username = ?",
                       (username,)).fetchone()
    if row is None or row["role"] == ROLE_SYSTEM or not row["active"]:
        raise PermissionDeniedError(f"{username} is not an account that can change data.")
    return dict(row)


def _active_role(conn, username: str):
    """The role of an active account, or None (unknown or disabled)."""
    row = conn.execute("SELECT role FROM users WHERE username = ? AND active = 1",
                       (username,)).fetchone()
    return row["role"] if row else None


_ID_ATTEMPTS = 5


def _new_sample_id() -> str:
    return f"LV-{uuid.uuid4().hex[:8].upper()}"


# ─────────────────────────────────────────────
# SAMPLES
# ─────────────────────────────────────────────

def register_sample(data: dict, user: str) -> str:
    """
    Register a manually submitted sample (status Pending, source Manual).
    Generates the sample ID; returns it. A generated ID that already exists
    is retried rather than silently dropped.
    """
    for _ in range(_ID_ATTEMPTS):
        sample = {**data, "sample_id": _new_sample_id(),
                  "status": STATUS_PENDING, "source": SOURCE_MANUAL}
        with core.transaction() as conn:
            _actor(conn, user)
            assignee = sample.get("assigned_to")
            if assignee and _active_role(conn, assignee) != domain.ROLE_LAB_TECH:
                raise ServiceError(f"Samples can only be assigned to active lab techs; "
                                   f"{assignee} isn't one.")
            if not samples.insert_sample(sample, conn=conn):
                continue  # ID collision — rolls back nothing, try a new ID
            audit.write_audit(conn, user, "SAMPLE_CREATED", "Sample Intake",
                           sample["sample_id"],
                           f"Registered: {sample['product_name']} | {sample['manufacturer']}")
        db.clear_data_caches()
        return sample["sample_id"]
    raise ServiceError("Could not generate a unique sample ID — please try again.")


def update_sample(sample_id: str, expected_version: int, user: str,
                  status: str = None, assigned_to: str = None, reason: str = "") -> bool:
    """
    Change a sample's status and/or assignee in one transaction.

    `expected_version` is the version the caller displayed. If the sample has
    changed since, nothing is written and ConcurrentUpdateError is raised —
    the user must reload instead of silently overwriting someone else's edit.
    Returns False when nothing actually changed (no write, no audit row).
    A real change needs a `reason`; each changed field is audited with its
    old value, new value and that reason.
    """
    try:
        return _update_sample(sample_id, expected_version, user, status, assigned_to,
                              (reason or "").strip())
    except (ConcurrentUpdateError, NotFoundError):
        # The caller's cached copy is stale — drop it so a reload shows the
        # current version instead of failing again.
        db.clear_data_caches()
        raise


def _update_sample(sample_id, expected_version, user, status, assigned_to, reason) -> bool:
    with core.transaction() as conn:
        actor = _actor(conn, user)
        row = conn.execute(f"""
            SELECT sample_id, status, assigned_to, version, {samples.REVIEW_COUNTS}
            FROM samples WHERE sample_id = ?""", (sample_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Sample {sample_id} no longer exists.")
        if row["version"] != expected_version:
            raise ConcurrentUpdateError(
                f"Sample {sample_id} was changed by someone else since you opened it. "
                "Your changes were not saved — reload and try again.")

        new_status = row["status"] if status is None else status
        new_assignee = row["assigned_to"] if assigned_to is None else assigned_to
        changes = []
        if new_status != row["status"]:
            changes.append(("STATUS_UPDATED", row["status"], new_status,
                            f"Status changed from {row['status']} to {new_status}"))
        if new_assignee != row["assigned_to"]:
            changes.append(("SAMPLE_ASSIGNED", row["assigned_to"], new_assignee,
                            f"Reassigned from {row['assigned_to'] or 'Unassigned'} "
                            f"to {new_assignee or 'Unassigned'}"))
        if not changes:
            return False
        assignee_role = _active_role(conn, new_assignee) if new_assignee else None
        denied = domain.change_error(actor, dict(row), new_status, new_assignee, assignee_role)
        if denied:
            raise PermissionDeniedError(denied)
        if not reason:
            raise ServiceError("Enter a reason for the change — it is recorded in the audit trail.")

        conn.execute("""
            UPDATE samples SET status = ?, assigned_to = ?, version = version + 1,
                               updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE sample_id = ? AND version = ?
        """, (new_status, new_assignee, sample_id, expected_version))
        for action, old, new, detail in changes:
            audit.write_audit(conn, user, action, "Sample Tracking", sample_id, detail,
                              old_value=old, new_value=new, reason=reason)

    db.clear_data_caches()
    return True


# ─────────────────────────────────────────────
# TEST RESULTS
# ─────────────────────────────────────────────

def record_result(data: dict, user: str) -> dict:
    """
    Evaluate and store a test result with its audit row; returns
    {id, status, spec}. `data` holds sample_id, test_name, result_value,
    outcome, tested_at and notes — never limits: for a numeric test the
    current specification for the sample's type × test is looked up here,
    and the result records which version it was judged against (ADR 0012).
    Only the assignee or an admin, while the sample is In Progress (ADR 0011).
    """
    with core.transaction() as conn:
        actor = _actor(conn, user)
        sample = conn.execute(
            "SELECT status, assigned_to, sample_type FROM samples WHERE sample_id = ?",
            (data["sample_id"],)).fetchone()
        if sample is None:
            raise NotFoundError(f"Sample {data['sample_id']} no longer exists.")
        denied = domain.result_entry_error(actor, dict(sample))
        if denied:
            raise PermissionDeniedError(denied)

        test, value, outcome = data["test_name"], data.get("result_value"), data.get("outcome")
        spec = (specifications.find_spec(sample["sample_type"], test, conn)
                if test in domain.QUANTITATIVE_TESTS else None)
        status, errors = domain.evaluate_result(test, value, outcome, spec)
        if errors:
            raise ServiceError(" ".join(errors))

        if spec:
            limits = (f"spec v{spec['version']}: {_fmt_limit(spec['spec_min'])} to "
                      f"{_fmt_limit(spec['spec_max'])} {spec['unit']}")
            shown = f"{value} {spec['unit']}"
        else:
            limits, shown = "pass/fail", outcome
        result_id = results.insert_test_result({
            "sample_id": data["sample_id"], "test_name": test, "result_value": value,
            "result_unit": spec["unit"] if spec else "N/A",
            "spec_min": spec["spec_min"] if spec else None,
            "spec_max": spec["spec_max"] if spec else None,
            "spec_id": spec["id"] if spec else None,
            "spec_version": spec["version"] if spec else None,
            "status": status, "tested_by": user,
            "tested_at": data["tested_at"], "notes": data.get("notes", ""),
        }, conn=conn)
        audit.write_audit(conn, user, "RESULT_LOGGED", "Test Results", data["sample_id"],
                          f"{test}: {shown} ({limits}) → {status}")
        investigation_id = None
        if status == domain.RESULT_OOS:
            # Every OOS opens an investigation, in the same transaction (ADR 0015).
            investigation_id = investigations.open_investigation(conn, result_id, user)
            audit.write_audit(conn, user, "OOS_INVESTIGATION_OPENED", "OOS Investigations",
                              data["sample_id"],
                              f"Investigation #{investigation_id} for result #{result_id} "
                              f"{test}: {shown}", new_value=domain.INVESTIGATION_OPEN)
    db.clear_data_caches()
    return {"id": result_id, "status": status, "spec": spec, "shown": shown,
            "investigation_id": investigation_id}


def _fmt_limit(value):
    return "—" if value is None else f"{value:g}"


# ─────────────────────────────────────────────
# RESULT REVIEW (E-SIGNATURE)
# ─────────────────────────────────────────────

class SignatureError(ServiceError):
    """The password check for an e-signature failed; nothing was signed."""


def sign_result(result_id: int, user: str, password: str, meaning: str,
                reason: str = "") -> dict:
    """
    Second-person review of a result (ADR 0014): the signer re-enters their
    password and states the meaning; a rejection needs a reason. Wrong
    passwords count toward the lockout. Returns {meaning, signed_at}.
    """
    reason = (reason or "").strip()
    if meaning not in domain.REVIEW_MEANINGS:
        raise ServiceError(f"Unknown signature meaning: {meaning}.")
    if meaning == domain.REVIEW_REJECTED and not reason:
        raise ServiceError("Enter a reason for rejecting the result.")

    with core.transaction() as conn:
        actor = _actor(conn, user)
        result = signatures.result_for_review(conn, result_id)
        if result is None:
            raise NotFoundError(f"Result #{result_id} no longer exists.")
        denied = domain.review_error(actor, result, meaning)
        if denied:
            raise PermissionDeniedError(denied)
        signed = _check_password(conn, users.login_account(conn, user), password,
                                 "SIGNATURE_FAILED", "Test Results", result["sample_id"])
        if signed:
            signed_at = signatures.insert_signature(conn, result_id, user, meaning,
                                                    reason or None)
            action = "RESULT_APPROVED" if meaning == domain.REVIEW_APPROVED else "RESULT_REJECTED"
            audit.write_audit(
                conn, user, action, "Test Results", result["sample_id"],
                f"Result #{result_id} {result['test_name']} ({result['status']}) by "
                f"{result['tested_by']}: {domain.SIGNATURE_MEANING_TEXT[meaning]}",
                old_value=domain.REVIEW_AWAITING, new_value=meaning, reason=reason or None)
    # The failed attempt is committed (count + audit) before refusing.
    db.clear_audit_cache()
    if not signed:
        raise SignatureError("Signature refused: wrong password, or the account is locked "
                             "after repeated failures. Nothing was signed.")
    db.clear_data_caches()
    return {"meaning": meaning, "signed_at": signed_at}


# ─────────────────────────────────────────────
# OOS INVESTIGATIONS
# ─────────────────────────────────────────────

def close_investigation(investigation_id: int, user: str, password: str, conclusion: str,
                        findings: str) -> dict:
    """
    Conclude an OOS investigation (ADR 0015): admin only, never on a result
    they logged, e-signed with their password (wrong passwords count toward
    the lockout). The conclusion fixes how the result may then be signed.
    Returns {conclusion, closed_at}.
    """
    findings = (findings or "").strip()
    if conclusion not in domain.CONCLUSIONS:
        raise ServiceError(f"Unknown conclusion: {conclusion}.")
    if not findings:
        raise ServiceError("Describe the investigation's findings before closing it.")

    with core.transaction() as conn:
        actor = _actor(conn, user)
        investigation = investigations.find_investigation(conn, investigation_id)
        if investigation is None:
            raise NotFoundError(f"Investigation #{investigation_id} no longer exists.")
        denied = domain.investigation_error(actor, investigation)
        if denied:
            raise PermissionDeniedError(denied)
        signed = _check_password(conn, users.login_account(conn, user), password,
                                 "SIGNATURE_FAILED", "OOS Investigations",
                                 investigation["sample_id"])
        if signed:
            closed_at = investigations.close_investigation(conn, investigation_id, user,
                                                           conclusion, findings)
            audit.write_audit(
                conn, user, "OOS_INVESTIGATION_CLOSED", "OOS Investigations",
                investigation["sample_id"],
                f"Investigation #{investigation_id} (result #{investigation['result_id']} "
                f"{investigation['test_name']} by {investigation['tested_by']}): "
                f"{domain.CONCLUSION_TEXT[conclusion]}",
                old_value=domain.INVESTIGATION_OPEN, new_value=conclusion, reason=findings)
    db.clear_audit_cache()
    if not signed:
        raise SignatureError("Signature refused: wrong password, or the account is locked "
                             "after repeated failures. The investigation is still open.")
    db.clear_data_caches()
    return {"conclusion": conclusion, "closed_at": closed_at}


# ─────────────────────────────────────────────
# SPECIFICATIONS
# ─────────────────────────────────────────────

def save_specification(sample_type: str, test_name: str, spec_min, spec_max, unit: str,
                       user: str, reason: str = "", expected_version: int = None) -> dict:
    """
    Create or change the specification for sample type × test (admin only).
    A change needs a reason and the version the admin was looking at
    (`expected_version`); it is audited with old and new limits. Results
    already recorded keep the limits they were judged against.
    """
    reason = (reason or "").strip()
    if sample_type not in domain.SAMPLE_TYPES:
        raise ServiceError(f"Unknown sample type: {sample_type}.")
    if test_name not in domain.QUANTITATIVE_TESTS:
        raise ServiceError(f"{test_name} is not a numeric test, so it has no specification.")
    if unit not in domain.UNITS:
        raise ServiceError(f"Unknown unit: {unit}.")
    invalid = domain.spec_error(spec_min, spec_max)
    if invalid:
        raise ServiceError(invalid)

    new_text = f"{_fmt_limit(spec_min)} to {_fmt_limit(spec_max)} {unit}"
    target = f"{sample_type} × {test_name}"
    with core.transaction() as conn:
        if not domain.is_admin(_actor(conn, user)):
            raise PermissionDeniedError("Only an admin can change specifications.")
        current = specifications.find_spec(sample_type, test_name, conn)
        if current is None:
            specifications.insert_spec(conn, sample_type, test_name, spec_min, spec_max,
                                       unit, user)
            audit.write_audit(conn, user, "SPEC_CREATED", "Specifications", target,
                              f"New specification: {new_text}", new_value=new_text,
                              reason=reason or None)
        else:
            old_text = (f"{_fmt_limit(current['spec_min'])} to "
                        f"{_fmt_limit(current['spec_max'])} {current['unit']}")
            if (current["spec_min"], current["spec_max"], current["unit"]) == \
                    (spec_min, spec_max, unit):
                return current
            if expected_version != current["version"]:
                raise ConcurrentUpdateError(
                    f"The {target} specification was changed by someone else "
                    f"(now v{current['version']}). Reload and try again.")
            if not reason:
                raise ServiceError("Enter a reason for changing the specification.")
            specifications.update_spec(conn, current["id"], expected_version,
                                       spec_min, spec_max, unit, user)
            audit.write_audit(conn, user, "SPEC_UPDATED", "Specifications", target,
                              f"Specification v{current['version']} → v{current['version'] + 1}",
                              old_value=old_text, new_value=new_text, reason=reason)
        saved = specifications.find_spec(sample_type, test_name, conn)
    db.clear_spec_cache()
    db.clear_audit_cache()
    return saved


# ─────────────────────────────────────────────
# PROTOCOLS
# ─────────────────────────────────────────────

def create_protocol(data: dict, user: str) -> int:
    """Create a protocol and its audit row together; returns its id."""
    protocol = {**data, "created_by": user, "created_at": core.utc_now()}
    with core.transaction() as conn:
        _actor(conn, user)
        protocol_id = protocols.insert_protocol(protocol, conn=conn)
        audit.write_audit(conn, user, "PROTOCOL_CREATED", "Protocols", protocol["name"],
                       f"New protocol: {protocol['name']} for {protocol['sample_type']}")
    db.clear_protocol_cache()
    db.clear_audit_cache()
    return protocol_id


# ─────────────────────────────────────────────
# FDA IMPORT
# ─────────────────────────────────────────────

def import_fda(limit: int = 100, only_if_empty: bool = False, user: str = SYSTEM_USER) -> dict:
    """
    Fetch openFDA recalls, simulate results (seed.py) and store the batch in
    one transaction (repo/fda_import.py, ADR 0002). With only_if_empty=True
    (the first-login auto-import) the write is skipped if samples exist.
    `user` is who started it (the admin, or whoever's first login triggered
    it); the audit row is credited to them.
    Returns {success, count, already_present, skipped, error[, not_needed]}.
    """
    try:
        records = seed.fetch_records(limit)
    except Exception as e:  # network/HTTP failure — reported to the user
        return {"success": False, "error": str(e), "count": 0}
    parsed, skipped = seed.parse_records(records, users.lab_techs())
    try:
        return fda_import.write_batch(parsed, skipped, user=user, only_if_empty=only_if_empty)
    finally:
        db.clear_data_caches()


# ─────────────────────────────────────────────
# EVENTS THAT CHANGE NO DATA
# ─────────────────────────────────────────────

def log_event(user: str, action: str, module: str, target_id: str = "", detail: str = ""):
    """Audit an event that changes no data, such as a report export."""
    with core.transaction() as conn:
        audit.write_audit(conn, user, action, module, target_id, detail)
    db.clear_audit_cache()


# ─────────────────────────────────────────────
# SIGN-IN
# ─────────────────────────────────────────────

def _check_password(conn, account: dict, password: str, failure_action: str,
                    module: str, target: str) -> bool:
    """
    The lockout policy (ADR 0013), shared by sign-in and e-signatures: True
    if `password` is right and the account isn't locked. Failures are counted
    and audited as `failure_action`; MAX_FAILED_LOGINS in a row lock the
    account for LOCKOUT_MINUTES (ACCOUNT_LOCKED). Success clears the count
    and upgrades an outdated hash. The caller must commit either way.
    """
    username = account["username"]
    if account["locked_until"] and account["locked_until"] > core.utc_now():
        audit.write_audit(conn, username, failure_action, module, target,
                          f"Account locked until {account['locked_until']}")
        return False
    if not passwords.verify(password, account["password"]):
        failures = account["failed_logins"] + 1
        if failures >= domain.MAX_FAILED_LOGINS:
            until = core.utc_after(minutes=domain.LOCKOUT_MINUTES)
            users.record_failure(conn, username, 0, until)
            audit.write_audit(conn, username, "ACCOUNT_LOCKED", "Auth", username,
                              f"{failures} failed password checks; locked until {until}")
        else:
            users.record_failure(conn, username, failures, None)
            audit.write_audit(conn, username, failure_action, module, target,
                              f"Wrong password ({failures} of {domain.MAX_FAILED_LOGINS})")
        return False
    upgrade = (passwords.hash_password(password)
               if passwords.needs_rehash(account["password"]) else None)
    users.record_success(conn, username, upgrade)
    return True


def sign_in(username: str, password: str):
    """
    Check credentials, apply the lockout policy and audit the attempt.
    Returns the user (without password hash) or None. The caller shows the
    same message for every failure, so it can't reveal which accounts exist.
    A failure on an unknown account is credited to `system` (after the same
    hashing work), with the attempted name as the target, truncated.
    """
    target = (username or "")[:64]
    with core.transaction() as conn:
        account = users.login_account(conn, username)
        if account is None:
            passwords.burn_time(password)
            audit.write_audit(conn, SYSTEM_USER, "LOGIN_FAILED", "Auth", target,
                              "Invalid username or password")
            user = None
        elif not account["active"]:
            passwords.burn_time(password)      # same work, same message as a wrong password
            audit.write_audit(conn, username, "LOGIN_FAILED", "Auth", target,
                              "Account disabled")
            user = None
        elif _check_password(conn, account, password, "LOGIN_FAILED", "Auth", target):
            audit.write_audit(conn, username, "LOGIN", "Auth", username, "Signed in")
            user = users.public(account)
        else:
            user = None
    db.clear_audit_cache()
    return user


def sign_out(username: str, idle: bool = False):
    if idle:
        log_event(username, "SESSION_TIMEOUT", "Auth", username,
                  f"Signed out after {domain.SESSION_IDLE_MINUTES} minutes idle")
    else:
        log_event(username, "LOGOUT", "Auth", username, "Signed out")


# ─────────────────────────────────────────────
# ACCOUNTS (audit 3.6, ADR 0017)
# ─────────────────────────────────────────────

def _managed_account(conn, admin: str, username: str) -> dict:
    """The account `admin` is about to change, after the permission check."""
    account = users.login_account(conn, username)
    denied = domain.account_change_error(_actor(conn, admin), account)
    if denied:
        raise PermissionDeniedError(denied)
    return account


def _required(reason: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise ServiceError("Enter a reason — it is recorded in the audit trail.")
    return reason


def _no_open_samples(conn, username: str, change: str):
    """Nothing may be left assigned to someone who can no longer work on it."""
    open_ids = samples.open_samples_assigned(conn, username)
    if open_ids:
        raise ServiceError(
            f"{username} still has {len(open_ids)} open sample(s) assigned: "
            f"{', '.join(open_ids[:10])}{' …' if len(open_ids) > 10 else ''}. "
            f"Reassign them on Sample Tracking before you {change}.")


def _check_new_password(username: str, password: str):
    error = domain.password_error(password, username)
    if error:
        raise ServiceError(error)


def create_user(username: str, role: str, temporary_password: str, admin: str):
    """A new login account; its temporary password must be changed at first sign-in."""
    username = (username or "").strip()
    error = domain.username_error(username)
    if error:
        raise ServiceError(error)
    if role not in domain.LOGIN_ROLES:
        raise ServiceError(f"Unknown role: {role}.")
    _check_new_password(username, temporary_password)
    with core.transaction() as conn:
        if not domain.is_admin(_actor(conn, admin)):
            raise PermissionDeniedError("Only an admin can manage accounts.")
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise ServiceError(f"The username {username} is already taken.")
        users.insert_user(conn, username, passwords.hash_password(temporary_password), role)
        audit.write_audit(conn, admin, "USER_CREATED", "Users", username,
                          f"Created {username} as {role}; temporary password must be changed",
                          new_value=role)
    db.clear_user_caches()
    db.clear_audit_cache()


def set_user_active(username: str, active: bool, admin: str, reason: str):
    """Disable or re-enable an account. A disabled account can't sign in or
    change data; it is kept because records refer to it."""
    reason = _required(reason)
    with core.transaction() as conn:
        account = _managed_account(conn, admin, username)
        if bool(account["active"]) == bool(active):
            return False
        if not active:
            _no_open_samples(conn, username, "disable the account")
        users.set_active(conn, username, active)
        audit.write_audit(conn, admin, "USER_ENABLED" if active else "USER_DISABLED", "Users",
                          username, f"{'Enabled' if active else 'Disabled'} {username}",
                          old_value="Active" if not active else "Disabled",
                          new_value="Active" if active else "Disabled", reason=reason)
    db.clear_user_caches()
    db.clear_audit_cache()
    return True


def change_role(username: str, role: str, admin: str, reason: str):
    """Change a login account's role. Samples are assigned only to lab techs,
    so a tech with open samples can't become an admin until they're reassigned."""
    reason = _required(reason)
    if role not in domain.LOGIN_ROLES:
        raise ServiceError(f"Unknown role: {role}.")
    with core.transaction() as conn:
        account = _managed_account(conn, admin, username)
        if account["role"] == role:
            return False
        if account["role"] == domain.ROLE_LAB_TECH:
            _no_open_samples(conn, username, "change the role")
        users.set_role(conn, username, role)
        audit.write_audit(conn, admin, "USER_ROLE_CHANGED", "Users", username,
                          f"Role of {username} changed", old_value=account["role"],
                          new_value=role, reason=reason)
    db.clear_user_caches()
    db.clear_audit_cache()
    return True


def reset_password(username: str, temporary_password: str, admin: str, reason: str):
    """Set a temporary password the user must change at next sign-in; clears any lockout."""
    reason = _required(reason)
    _check_new_password(username, temporary_password)
    with core.transaction() as conn:
        _managed_account(conn, admin, username)
        users.set_password(conn, username, passwords.hash_password(temporary_password),
                           must_change=True)
        audit.write_audit(conn, admin, "PASSWORD_RESET", "Users", username,
                          f"Temporary password set for {username}; must be changed at "
                          "next sign-in", reason=reason)
    db.clear_user_caches()
    db.clear_audit_cache()


def unlock_user(username: str, admin: str, reason: str):
    """End a lockout (ADR 0013) before it expires. Returns False if not locked."""
    reason = _required(reason)
    with core.transaction() as conn:
        account = _managed_account(conn, admin, username)
        locked = account["locked_until"] and account["locked_until"] > core.utc_now()
        if not (locked or account["failed_logins"]):
            return False
        users.unlock(conn, username)
        audit.write_audit(conn, admin, "ACCOUNT_UNLOCKED", "Users", username,
                          f"Unlocked {username} ({account['failed_logins']} failed attempts, "
                          f"locked until {account['locked_until'] or '—'})", reason=reason)
    db.clear_user_caches()
    db.clear_audit_cache()
    return True


def change_password(username: str, current: str, new: str):
    """
    A user changes their own password; required after an admin set it.
    The current password is checked with the sign-in lockout policy.
    """
    _check_new_password(username, new)
    if new == current:
        raise ServiceError("Choose a password different from the current one.")
    with core.transaction() as conn:
        _actor(conn, username)
        ok = _check_password(conn, users.login_account(conn, username), current,
                             "PASSWORD_CHANGE_FAILED", "Auth", username)
        if ok:
            users.set_password(conn, username, passwords.hash_password(new), must_change=False)
            audit.write_audit(conn, username, "PASSWORD_CHANGED", "Auth", username,
                              "Changed own password")
    # A failed attempt is committed (count + audit) before refusing.
    db.clear_audit_cache()
    db.clear_user_caches()
    if not ok:
        raise SignatureError("Current password is wrong, or the account is locked after "
                             "repeated failures. The password was not changed.")
