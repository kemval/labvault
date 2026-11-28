"""Sample Tracking and Intake through the real UI (audit H8)."""
import pytest

import db
import services
from domain import TERMINAL_STATUSES
from repo.specifications import seed_specifications
from test_app_login import login, run_app
from test_services import BASE, RESULT, audit, rows


@pytest.fixture
def tracking(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    sample_id = services.register_sample(BASE, "admin")
    at = login(run_app(), "kembly", "lab2024")
    at.sidebar.radio[0].set_value("🔬  Sample Tracking").run()
    assert not at.exception, at.exception
    return open_sample_panel(at, sample_id), sample_id


def open_sample_panel(at, sample_id):
    at.selectbox(key="trk_open").set_value(sample_id).run()
    assert not at.exception, at.exception
    return at


def save(at, sample_id, status, reason="Analysis started"):
    at.selectbox(key=f"status_{sample_id}").set_value(status).run()
    at.text_input(key=f"reason_{sample_id}").set_value(reason)
    if status in TERMINAL_STATUSES:
        at.checkbox(key=f"confirm_{sample_id}").check().run()
    at.button(key=f"save_{sample_id}").click().run()
    assert not at.exception, at.exception
    return at


def test_save_updates_sample_and_audit(tracking):
    at, sample_id = tracking
    save(at, sample_id, "In Progress")
    [s] = rows("SELECT * FROM samples")
    assert (s["status"], s["version"]) == ("In Progress", 2)
    assert audit("STATUS_UPDATED")[0]["user"] == "kembly"


def test_concurrent_edit_is_rejected_and_other_users_change_kept(tracking):
    at, sample_id = tracking
    # Someone else saves after this page was rendered (e.g. in another process).
    services.update_sample(sample_id, 1, "admin", status="Rejected", reason="test")
    db.clear_data_caches()

    at = save(at, sample_id, "In Progress")

    assert any("changed by someone else" in e.value for e in at.error)
    assert any("Someone else changed this sample" in w.value for w in at.warning)
    assert rows("SELECT status, version FROM samples") == [{"status": "Rejected", "version": 2}]
    assert [a["user"] for a in audit("STATUS_UPDATED")] == ["admin"]


def test_reload_adopts_current_values_then_saves(tracking):
    at, sample_id = tracking
    services.update_sample(sample_id, 1, "admin", status="In Progress", reason="test")
    db.clear_data_caches()
    at.run()

    at.button(key=f"reload_btn_{sample_id}").click().run()
    assert at.selectbox(key=f"status_{sample_id}").value == "In Progress"
    assert not any("Someone else changed" in w.value for w in at.warning)

    save(at, sample_id, "Rejected")
    assert rows("SELECT status, version FROM samples") == [{"status": "Rejected", "version": 3}]


def test_consecutive_saves_by_same_user_both_succeed(tracking):
    at, sample_id = tracking
    save(at, sample_id, "In Progress")
    seed_specifications()
    saved = services.record_result({**RESULT, "sample_id": sample_id}, "kembly")
    services.sign_result(saved["id"], "carlos", "lab2024", "Approved")  # needed to complete
    at.run()
    save(at, sample_id, "Completed")
    assert rows("SELECT status, version FROM samples") == [{"status": "Completed", "version": 3}]
    assert not at.error


def test_intake_form_registers_sample_with_audit(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    fresh_db.insert_sample({**BASE, "sample_id": "S-0", "status": "Pending", "source": "Manual"})
    at = login(run_app(), "kembly", "lab2024")
    at.sidebar.radio[0].set_value("🧫  Sample Intake").run()
    [product, manufacturer] = [w for w in at.text_input if w.label.endswith("*")]
    product.input("Amoxicillin 250mg")
    manufacturer.input("Acme")
    next(b for b in at.button if b.label == "Register Sample").click().run()
    assert not at.exception, at.exception

    [new] = rows("SELECT * FROM samples WHERE sample_id != 'S-0'")
    assert new["product_name"] == "Amoxicillin 250mg"
    assert audit("SAMPLE_CREATED")[0]["target_id"] == new["sample_id"]
    assert any(new["sample_id"] in s.value for s in at.success)


def test_status_save_keeps_unassigned_sample_unassigned(fresh_db, settings):
    settings(demo="true")
    fresh_db.seed_users(demo=True)
    sample_id = services.register_sample({**BASE, "assigned_to": None}, "admin")
    at = login(run_app(), "kembly", "lab2024")
    at.sidebar.radio[0].set_value("🔬  Sample Tracking").run()
    open_sample_panel(at, sample_id)
    assert at.selectbox(key=f"assign_{sample_id}").value == "Unassigned"

    save(at, sample_id, "In Progress")

    [s] = rows("SELECT * FROM samples")
    assert (s["status"], s["assigned_to"]) == ("In Progress", None)
    assert audit("SAMPLE_ASSIGNED") == []


# ── finding samples in SQL (audit M2, ADR 0016) ──────────────────────────────

def bulk_samples(n, vary=lambda i: {}):
    """n samples S-00000… straight into the table (the service would audit each)."""
    from repo import core
    cols = ("sample_id", "product_name", "lot_number", "manufacturer", "sample_type",
            "recall_class", "priority", "reason_for_recall", "collection_date", "status",
            "assigned_to", "protocol_id", "notes", "source")
    data = [{**BASE, "status": "Pending", "source": "Manual", "sample_id": f"S-{i:05d}",
             **vary(i)} for i in range(n)]
    with core.transaction() as conn:
        conn.executemany(f"INSERT INTO samples ({', '.join(cols)}) VALUES "
                         f"({', '.join(':' + c for c in cols)})", data)
    db.clear_data_caches()


def ids(found):
    return [r["sample_id"] for r in found[0]]


@pytest.fixture
def mixed(lab_db):
    priorities = ["Minor", "Critical", "Major"]
    bulk_samples(6, lambda i: {
        "priority": priorities[i % 3],
        "assigned_to": [None, "kembly", "carlos"][i % 3],
        "status": "In Progress" if i % 2 else "Pending",
        "product_name": ["Metformin 500mg", "Amox 50%_off", "Ibuprofen"][i % 3],
        "collection_date": f"2026-01-{10 - i:02d}"})
    return lab_db


def test_find_samples_filters_in_sql(mixed):
    from repo.samples import find_samples
    assert ids(find_samples(status="In Progress")) == ["S-00005", "S-00003", "S-00001"]
    assert ids(find_samples(priority="Critical")) == ["S-00004", "S-00001"]
    assert ids(find_samples(assigned_to="kembly")) == ["S-00004", "S-00001"]
    assert ids(find_samples(unassigned=True)) == ["S-00003", "S-00000"]
    assert ids(find_samples(search="metFORMIN")) == ["S-00003", "S-00000"]
    assert ids(find_samples(search="s-0000")) == ids(find_samples())       # ID, any case


def test_find_samples_search_treats_wildcards_literally(mixed):
    from repo.samples import find_samples
    assert ids(find_samples(search="50%_")) == ["S-00004", "S-00001"]
    assert find_samples(search="%") == find_samples(search="50%")
    assert ids(find_samples(search="_")) == ["S-00004", "S-00001"]


def test_find_samples_sorts_and_pages(mixed):
    from repo.samples import find_samples
    assert ids(find_samples(sort="priority")) == \
        ["S-00004", "S-00001", "S-00005", "S-00002", "S-00003", "S-00000"]
    assert ids(find_samples(sort="collection"))[0] == "S-00005"            # oldest first
    assert ids(find_samples(sort="sample_id"))[0] == "S-00000"
    page1, page2 = find_samples(limit=4), find_samples(limit=4, offset=4)
    assert (page1[1], page2[1]) == (6, 6)
    assert ids(page1) + ids(page2) == ids(find_samples())


def test_sample_detail_includes_protocol_and_review_counts(lab_db):
    from repo import protocols
    from repo.samples import sample_detail
    pid = protocols.insert_protocol({"name": "USP <71> Sterility", "sample_type": "Injectable",
                                     "description": "", "steps": "", "created_by": "admin",
                                     "created_at": "2026-01-01"})
    sid = services.register_sample({**BASE, "protocol_id": pid}, "admin")
    s = sample_detail(sid)
    assert (s["protocol_name"], s["result_count"], s["unreviewed_count"]) == \
        ("USP <71> Sterility", 0, 0)
    assert sample_detail("nope") is None


# ── the page ────────────────────────────────────────────────────────────────

def tracking_page(user="kembly"):
    at = login(run_app(), user, "admin123" if user == "admin" else "lab2024")
    at.sidebar.radio[0].set_value("🔬  Sample Tracking").run()
    assert not at.exception, at.exception
    return at


def table_ids(at):
    return list(at.dataframe[0].value["Sample ID"])


def test_rejecting_needs_confirmation(tracking):
    at, sample_id = tracking
    at.selectbox(key=f"status_{sample_id}").set_value("Rejected").run()
    at.text_input(key=f"reason_{sample_id}").set_value("Damaged in transit")
    assert at.button(key=f"save_{sample_id}").disabled
    assert rows("SELECT status FROM samples") == [{"status": "Pending"}]

    at.checkbox(key=f"confirm_{sample_id}").check().run()
    at.button(key=f"save_{sample_id}").click().run()
    assert rows("SELECT status FROM samples") == [{"status": "Rejected"}]
    assert any(f"Saved changes to {sample_id}" in s.value for s in at.success)


def test_non_terminal_change_needs_no_confirmation(tracking):
    at, sample_id = tracking
    at.selectbox(key=f"status_{sample_id}").set_value("In Progress").run()
    assert not at.checkbox and not at.button(key=f"save_{sample_id}").disabled


def test_detail_shows_protocol(lab_db, settings):
    from repo import protocols
    settings(demo="true")
    pid = protocols.insert_protocol({"name": "USP <71> Sterility", "sample_type": "Injectable",
                                     "description": "", "steps": "", "created_by": "admin",
                                     "created_at": "2026-01-01"})
    sid = services.register_sample({**BASE, "protocol_id": pid}, "admin")
    at = open_sample_panel(tracking_page(), sid)
    assert any(f"USP &lt;71&gt; Sterility (#{pid})" in m.value for m in at.markdown)


def test_my_samples_and_unassigned_views(mixed, settings):
    settings(demo="true")
    at = tracking_page()
    assert len(table_ids(at)) == 6
    at.radio(key="trk_show").set_value("Assigned to me").run()
    assert table_ids(at) == ["S-00004", "S-00001"]
    at.radio(key="trk_show").set_value("Unassigned").run()
    assert table_ids(at) == ["S-00003", "S-00000"]


def test_other_techs_sample_opens_read_only(mixed, settings):
    settings(demo="true")
    at = open_sample_panel(tracking_page(), "S-00002")                    # carlos's
    assert any("only the assignee" in c.value for c in at.caption)
    assert not [b for b in at.button if b.key == "save_S-00002"]


def test_page_stays_small_at_5000_samples(lab_db, settings):
    import time
    settings(demo="true")
    bulk_samples(5000)
    at = tracking_page("admin")
    assert any("5,000 sample(s) found" in m.value for m in at.markdown)
    assert table_ids(at) == [f"S-{i:05d}" for i in range(4999, 4974, -1)]
    assert len(at.selectbox(key="trk_open").options) == 25

    at.number_input(key="trk_page").set_value(200)
    started = time.perf_counter()
    at.run()
    assert time.perf_counter() - started < 2.0
    assert table_ids(at)[-1] == "S-00000"

    # Changing a filter goes back to page 1.
    at.selectbox(key="trk_priority").set_value("Major").run()
    assert at.number_input(key="trk_page").value == 1


def test_opened_sample_closes_when_it_leaves_the_page(mixed, settings):
    settings(demo="true")
    at = open_sample_panel(tracking_page(), "S-00002")
    at.radio(key="trk_show").set_value("Assigned to me").run()
    assert at.selectbox(key="trk_open").value is None
    assert not at.exception
