import glob
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import dedupe_simulated_results as dedupe  # noqa: E402


def add_sample(db, sample_id, source="FDA"):
    db.insert_sample({
        "sample_id": sample_id, "product_name": "P", "lot_number": "", "manufacturer": "M",
        "sample_type": "Tablet", "recall_class": "Class II", "priority": "Major",
        "reason_for_recall": "", "collection_date": "2024-01-01", "status": "Pending",
        "assigned_to": "kembly", "protocol_id": None, "notes": "", "source": source,
    })


def add_result(db, sample_id, value, notes, test="Potency (% Label Claim)"):
    db.insert_test_result({
        "sample_id": sample_id, "test_name": test, "result_value": value,
        "result_unit": "%", "spec_min": 90.0, "spec_max": 110.0,
        "status": "Pass" if 90 <= value <= 110 else "Fail (OOS)",
        "tested_by": "kembly", "tested_at": "2024-01-02", "notes": notes,
    })


@pytest.fixture
def dup_db(lab_db):
    add_sample(lab_db, "D-1")
    add_result(lab_db, "D-1", 86.2, "Result 86.2% below 90% specification.")  # id 1, kept
    add_result(lab_db, "D-1", 101.1, "Within specification.")                 # id 2, simulated dupe
    add_result(lab_db, "D-1", 99.0, "Retest after column change, analyst B")  # id 3, manual retest
    add_sample(lab_db, "M-1", source="Manual")
    add_result(lab_db, "M-1", 95.0, "Within specification.")                  # id 4
    add_result(lab_db, "M-1", 96.0, "Within specification.")                  # id 5, manual sample
    return lab_db.DB_PATH


def result_ids(path):
    conn = sqlite3.connect(path)
    ids = [r[0] for r in conn.execute("SELECT id FROM test_results ORDER BY id")]
    conn.close()
    return ids


def test_dry_run_changes_nothing(dup_db, capsys):
    assert dedupe.main([dup_db]) == 0
    assert "1 duplicate simulated result(s) found" in capsys.readouterr().out
    assert result_ids(dup_db) == [1, 2, 3, 4, 5]
    assert not glob.glob(dup_db + ".backup-*")


def test_apply_removes_only_simulated_duplicates_with_backup_and_audit(dup_db):
    assert dedupe.main([dup_db, "--apply", "--user", "admin"]) == 0

    assert result_ids(dup_db) == [1, 3, 4, 5]
    backups = glob.glob(dup_db + ".backup-*")
    assert len(backups) == 1 and result_ids(backups[0]) == [1, 2, 3, 4, 5]
    conn = sqlite3.connect(dup_db)
    audit = conn.execute(
        "SELECT user, detail FROM audit_trail WHERE action='RESULTS_DEDUPLICATED'").fetchall()
    conn.close()
    assert len(audit) == 1 and audit[0][0] == "admin" and "Removed 1" in audit[0][1]


def test_apply_requires_user(dup_db):
    with pytest.raises(SystemExit):
        dedupe.main([dup_db, "--apply"])



def test_apply_rejects_unknown_user_before_backup(dup_db):
    # The audit trail references users, so a typo must fail before anything is written.
    assert dedupe.main([dup_db, "--apply", "--user", "ghost"]) == 2
    assert result_ids(dup_db) == [1, 2, 3, 4, 5]
    assert glob.glob(dup_db + ".backup-*") == []

def test_every_simulator_note_is_recognised():
    import random
    import seed
    random.seed(0)
    reasons = ["dissolution failure", "superpotent", "subpotent", "sterility", "particulate",
               "ph out of range", "mislabeled", "unknown reason"]
    for reason in reasons * 20:
        for r in seed.simulate_test_results("X", reason, "Tablet", "kembly", "2024-01-01"):
            assert dedupe.SIMULATOR_NOTES.match(r["notes"]), r["notes"]
