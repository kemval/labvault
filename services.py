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
from domain import ROLE_SYSTEM, SOURCE_MANUAL, STATUS_PENDING, SYSTEM_USER
import seed
from repo import audit, core, fda_import, protocols, results, samples, users


class ServiceError(Exception):
    """A business-rule failure the UI should show to the user."""


class NotFoundError(ServiceError):
    pass


class ConcurrentUpdateError(ServiceError):
    """The record changed since the caller read it; reload and retry."""


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
        row = conn.execute(
            "SELECT status, assigned_to, version FROM samples WHERE sample_id = ?",
            (sample_id,)).fetchone()
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

def record_result(data: dict, user: str, audit_detail: str) -> int:
    """Store a validated test result and its audit row together; returns its id."""
    with core.transaction() as conn:
        if conn.execute("SELECT 1 FROM samples WHERE sample_id = ?",
                        (data["sample_id"],)).fetchone() is None:
            raise NotFoundError(f"Sample {data['sample_id']} no longer exists.")
        result_id = results.insert_test_result({**data, "tested_by": user}, conn=conn)
        audit.write_audit(conn, user, "RESULT_LOGGED", "Test Results",
                       data["sample_id"], audit_detail)
    db.clear_data_caches()
    return result_id


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
    Check credentials and audit the attempt. Returns the user dict or None.
    A failure is credited to the account when it exists (so repeated
    failures on one account are visible), otherwise to `system`; the
    attempted name is kept as the target, truncated.
    """
    user = users.authenticate(username, password)
    with core.transaction() as conn:
        if user:
            audit.write_audit(conn, user["username"], "LOGIN", "Auth", user["username"],
                              "Signed in")
        else:
            known = conn.execute(
                "SELECT 1 FROM users WHERE username = ? AND role != ?",
                (username, ROLE_SYSTEM)).fetchone()
            audit.write_audit(conn, username if known else SYSTEM_USER, "LOGIN_FAILED", "Auth",
                              (username or "")[:64], "Invalid username or password")
    db.clear_audit_cache()
    return user


def sign_out(username: str):
    log_event(username, "LOGOUT", "Auth", username, "Signed out")
