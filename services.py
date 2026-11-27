"""
services.py — LabVault use cases.

Every function that changes data runs in ONE transaction that also writes
its audit row, so a change can never be saved without its audit entry (or
the reverse). Caches are cleared only after a successful commit.
Views call these functions; they never write to the database directly.
See docs/adr/0005-service-layer.md.
"""

import uuid
from datetime import datetime

import db


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
                  "status": "Pending", "source": "Manual"}
        with db.transaction() as conn:
            if not db.insert_sample(sample, conn=conn):
                continue  # ID collision — rolls back nothing, try a new ID
            db.write_audit(conn, user, "SAMPLE_CREATED", "Sample Intake",
                           sample["sample_id"],
                           f"Registered: {sample['product_name']} | {sample['manufacturer']}")
        db.clear_data_caches()
        return sample["sample_id"]
    raise ServiceError("Could not generate a unique sample ID — please try again.")


def update_sample(sample_id: str, expected_version: int, user: str,
                  status: str = None, assigned_to: str = None) -> bool:
    """
    Change a sample's status and/or assignee in one transaction.

    `expected_version` is the version the caller displayed. If the sample has
    changed since, nothing is written and ConcurrentUpdateError is raised —
    the user must reload instead of silently overwriting someone else's edit.
    Returns False when nothing actually changed (no write, no audit row).
    """
    try:
        return _update_sample(sample_id, expected_version, user, status, assigned_to)
    except (ConcurrentUpdateError, NotFoundError):
        # The caller's cached copy is stale — drop it so a reload shows the
        # current version instead of failing again.
        db.clear_data_caches()
        raise


def _update_sample(sample_id, expected_version, user, status, assigned_to) -> bool:
    with db.transaction() as conn:
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
            changes.append(("STATUS_UPDATED",
                            f"Status changed from {row['status']} to {new_status}"))
        if new_assignee != row["assigned_to"]:
            changes.append(("SAMPLE_ASSIGNED",
                            f"Reassigned from {row['assigned_to']} to {new_assignee}"))
        if not changes:
            return False

        conn.execute("""
            UPDATE samples SET status = ?, assigned_to = ?, version = version + 1
            WHERE sample_id = ? AND version = ?
        """, (new_status, new_assignee, sample_id, expected_version))
        for action, detail in changes:
            db.write_audit(conn, user, action, "Sample Tracking", sample_id, detail)

    db.clear_data_caches()
    return True


# ─────────────────────────────────────────────
# TEST RESULTS
# ─────────────────────────────────────────────

def record_result(data: dict, user: str, audit_detail: str) -> int:
    """Store a validated test result and its audit row together; returns its id."""
    with db.transaction() as conn:
        if conn.execute("SELECT 1 FROM samples WHERE sample_id = ?",
                        (data["sample_id"],)).fetchone() is None:
            raise NotFoundError(f"Sample {data['sample_id']} no longer exists.")
        result_id = db.insert_test_result({**data, "tested_by": user}, conn=conn)
        db.write_audit(conn, user, "RESULT_LOGGED", "Test Results",
                       data["sample_id"], audit_detail)
    db.clear_data_caches()
    return result_id


# ─────────────────────────────────────────────
# PROTOCOLS
# ─────────────────────────────────────────────

def create_protocol(data: dict, user: str) -> int:
    """Create a protocol and its audit row together; returns its id."""
    protocol = {**data, "created_by": user,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    with db.transaction() as conn:
        protocol_id = db.insert_protocol(protocol, conn=conn)
        db.write_audit(conn, user, "PROTOCOL_CREATED", "Protocols", protocol["name"],
                       f"New protocol: {protocol['name']} for {protocol['sample_type']}")
    db.get_all_protocols.clear()
    db.get_audit_trail.clear()
    return protocol_id
