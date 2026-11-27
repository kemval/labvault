"""Dashboard KPIs reflect the whole database (audit H1)."""
from test_app_login import login, run_app, no_network  # noqa: F401


def add_samples(db, n, status="Pending"):
    for i in range(n):
        db.insert_sample({
            "sample_id": f"S-{status}-{i}", "product_name": "P", "lot_number": "",
            "manufacturer": "M", "sample_type": "Tablet", "recall_class": "Class II",
            "priority": "Major", "reason_for_recall": "", "collection_date": "2026-01-01",
            "status": status, "assigned_to": "kembly", "protocol_id": None,
            "notes": "", "source": "Manual",
        })


def metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


def test_total_samples_counts_every_sample(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    add_samples(fresh_db, 7, "Pending")
    add_samples(fresh_db, 5, "Completed")

    at = login(run_app(), "admin", "admin123")

    assert metric(at, "Total Samples") == "12"
    assert metric(at, "Pending") == "7"
    assert metric(at, "Completed") == "5"
    assert not any("No samples loaded yet" in w.value for w in at.warning)
