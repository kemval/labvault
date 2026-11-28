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
                  specifications, users)


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
    row = conn.execute("SELECT username, role FROM users WHERE username = ?",
                       (username,)).fetchone()
    if row is None or row["role"] == ROLE_SYSTEM:
        raise PermissionDeniedError(f"{username} is not an account that can change data.")
    return dict(row)


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
        row = conn.execute("""
            SELECT sample_id, status, assigned_to, version,
                   (SELECT COUNT(*) FROM test_results t
                    WHERE t.sample_id = samples.sample_id) AS result_count
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
        assignee = conn.execute("SELECT role FROM users WHERE username = ?",
                                (new_assignee,)).fetchone() if new_assignee else None
        denied = domain.change_error(actor, dict(row), new_status, new_assignee,
                                     assignee["role"] if assignee else None)
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
    db.clear_data_caches()
    return {"id": result_id, "status": status, "spec": spec, "shown": shown}


def _fmt_limit(value):
    return "—" if value is None else f"{value:g}"


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

def sign_in(username: str, password: str):
    """
    Check credentials, apply the lockout policy and audit the attempt.
    Returns the user (without password hash) or None. The caller shows the
    same message for every failure, so it can't reveal which accounts exist.

    - MAX_FAILED_LOGINS consecutive failures lock the account for
      LOCKOUT_MINUTES (ACCOUNT_LOCKED); attempts while locked are refused
      without checking the password.
    - A failure is credited to the account when it exists, otherwise to
      `system`; the attempted name is kept as the target, truncated.
    - A successful sign-in clears the count and upgrades an old hash.
    """
    target = (username or "")[:64]
    with core.transaction() as conn:
        account = users.login_account(conn, username)
        now = core.utc_now()
        if account is None:
            passwords.burn_time(password)
            audit.write_audit(conn, SYSTEM_USER, "LOGIN_FAILED", "Auth", target,
                              "Invalid username or password")
            user = None
        elif account["locked_until"] and account["locked_until"] > now:
            audit.write_audit(conn, username, "LOGIN_FAILED", "Auth", target,
                              f"Account locked until {account['locked_until']}")
            user = None
        elif not passwords.verify(password, account["password"]):
            failures = account["failed_logins"] + 1
            if failures >= domain.MAX_FAILED_LOGINS:
                until = core.utc_after(minutes=domain.LOCKOUT_MINUTES)
                users.record_failure(conn, username, 0, until)
                audit.write_audit(conn, username, "ACCOUNT_LOCKED", "Auth", target,
                                  f"{failures} failed sign-ins; locked until {until}")
            else:
                users.record_failure(conn, username, failures, None)
                audit.write_audit(conn, username, "LOGIN_FAILED", "Auth", target,
                                  f"Invalid username or password ({failures} of "
                                  f"{domain.MAX_FAILED_LOGINS})")
            user = None
        else:
            upgrade = (passwords.hash_password(password)
                       if passwords.needs_rehash(account["password"]) else None)
            users.record_success(conn, username, upgrade)
            audit.write_audit(conn, username, "LOGIN", "Auth", username, "Signed in")
            user = users.public(account)
    db.clear_audit_cache()
    return user


def sign_out(username: str, idle: bool = False):
    if idle:
        log_event(username, "SESSION_TIMEOUT", "Auth", username,
                  f"Signed out after {domain.SESSION_IDLE_MINUTES} minutes idle")
    else:
        log_event(username, "LOGOUT", "Auth", username, "Signed out")
