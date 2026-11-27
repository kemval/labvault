"""Service layer: atomic change + audit, optimistic concurrency (audit A1, C3a, H8)."""
import pytest

import db
import services
from repo import audit as audit_repo, core
from repo.samples import insert_sample

BASE = {
    "product_name": "Metformin 500mg", "lot_number": "AB1", "manufacturer": "Acme",
    "sample_type": "Tablet", "recall_class": "Class II", "priority": "Major",
    "reason_for_recall": "", "collection_date": "2026-01-01", "assigned_to": "kembly",
    "protocol_id": None, "notes": "",
}


def rows(sql, params=()):
    conn = core.get_conn()
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def audit(action=None):
    sql = "SELECT * FROM audit_trail" + (" WHERE action = ?" if action else "") + " ORDER BY id"
    return rows(sql, (action,) if action else ())


@pytest.fixture
def failing_audit(monkeypatch):
    """Make the audit insert fail, as a crash between the two writes would."""
    def boom(*a, **k):
        raise RuntimeError("audit write failed")
    monkeypatch.setattr(audit_repo, "write_audit", boom)


# ── register_sample ────────────────────────────────────────────────────────

def test_register_sample_writes_sample_and_audit(lab_db):
    sample_id = services.register_sample(BASE, "kembly")
    [s] = rows("SELECT * FROM samples")
    assert s["sample_id"] == sample_id and sample_id.startswith("LV-")
    assert (s["status"], s["source"], s["version"], s["is_simulated"]) == ("Pending", "Manual", 1, 0)
    [a] = audit("SAMPLE_CREATED")
    assert (a["user"], a["target_id"]) == ("kembly", sample_id)


def test_register_sample_rolls_back_when_audit_fails(lab_db, failing_audit):
    with pytest.raises(RuntimeError):
        services.register_sample(BASE, "kembly")
    assert rows("SELECT * FROM samples") == []


def test_register_sample_retries_id_collision(lab_db, monkeypatch):
    insert_sample({**BASE, "sample_id": "LV-TAKEN", "status": "Pending", "source": "Manual"})
    ids = iter(["LV-TAKEN", "LV-FRESH"])
    monkeypatch.setattr(services, "_new_sample_id", lambda: next(ids))

    assert services.register_sample(BASE, "kembly") == "LV-FRESH"
    assert len(audit("SAMPLE_CREATED")) == 1


# ── update_sample ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_id(lab_db):
    return services.register_sample(BASE, "admin")


def test_update_changes_both_fields_atomically_with_old_and_new_values(sample_id):
    assert services.update_sample(sample_id, 1, "admin", status="In Progress", assigned_to="maria")

    [s] = rows("SELECT * FROM samples")
    assert (s["status"], s["assigned_to"], s["version"]) == ("In Progress", "maria", 2)
    assert audit("STATUS_UPDATED")[0]["detail"] == "Status changed from Pending to In Progress"
    assert audit("SAMPLE_ASSIGNED")[0]["detail"] == "Reassigned from kembly to maria"


def test_update_rolls_back_when_audit_fails(sample_id, failing_audit):
    with pytest.raises(RuntimeError):
        services.update_sample(sample_id, 1, "admin", status="Completed")
    [s] = rows("SELECT * FROM samples")
    assert (s["status"], s["version"]) == ("Pending", 1)


def test_stale_update_is_rejected_and_first_writer_wins(sample_id):
    services.update_sample(sample_id, 1, "kembly", status="In Progress")

    with pytest.raises(services.ConcurrentUpdateError, match="changed by someone else"):
        services.update_sample(sample_id, 1, "carlos", status="Rejected")

    [s] = rows("SELECT * FROM samples")
    assert (s["status"], s["version"]) == ("In Progress", 2)
    assert [a["user"] for a in audit("STATUS_UPDATED")] == ["kembly"]


def test_rejected_update_clears_stale_cache(sample_id):
    assert db.get_all_samples()[0]["version"] == 1          # cached copy
    conn = core.get_conn()                                    # another process writes
    conn.execute("UPDATE samples SET version = 2, status = 'Completed'")
    conn.commit()
    conn.close()

    with pytest.raises(services.ConcurrentUpdateError):
        services.update_sample(sample_id, 1, "admin", status="Rejected")
    assert db.get_all_samples()[0]["version"] == 2           # reload sees the truth


def test_noop_update_writes_nothing(sample_id):
    before = len(audit())
    assert services.update_sample(sample_id, 1, "admin",
                                  status="Pending", assigned_to="kembly") is False
    assert rows("SELECT version FROM samples") == [{"version": 1}]
    assert len(audit()) == before


def test_update_of_missing_sample(lab_db):
    with pytest.raises(services.NotFoundError):
        services.update_sample("NOPE", 1, "admin", status="Completed")


# ── record_result / create_protocol ────────────────────────────────────────

RESULT = {"test_name": "pH", "result_value": 6.0, "result_unit": "pH", "spec_min": 4.5,
          "spec_max": 7.5, "status": "Pass", "tested_at": "2026-01-02", "notes": ""}


def test_record_result_writes_result_and_audit(sample_id):
    services.record_result({**RESULT, "sample_id": sample_id}, "kembly", "pH: 6.0 → Pass")
    [r] = rows("SELECT * FROM test_results")
    assert (r["tested_by"], r["status"]) == ("kembly", "Pass")
    assert audit("RESULT_LOGGED")[0]["detail"] == "pH: 6.0 → Pass"


def test_record_result_rolls_back_when_audit_fails(sample_id, failing_audit):
    with pytest.raises(RuntimeError):
        services.record_result({**RESULT, "sample_id": sample_id}, "kembly", "x")
    assert rows("SELECT * FROM test_results") == []


def test_record_result_for_missing_sample(lab_db):
    with pytest.raises(services.NotFoundError):
        services.record_result({**RESULT, "sample_id": "NOPE"}, "kembly", "x")


def test_create_protocol_writes_protocol_and_audit(lab_db):
    services.create_protocol({"name": "KF Water", "sample_type": "Powder",
                              "description": "", "steps": "1. Titrate"}, "admin")
    [p] = rows("SELECT * FROM protocols")
    assert p["created_by"] == "admin" and p["created_at"]
    assert audit("PROTOCOL_CREATED")[0]["target_id"] == "KF Water"


def test_create_protocol_rolls_back_when_audit_fails(lab_db, failing_audit):
    with pytest.raises(RuntimeError):
        services.create_protocol({"name": "X", "sample_type": "Tablet",
                                  "description": "", "steps": ""}, "admin")
    assert rows("SELECT * FROM protocols") == []
