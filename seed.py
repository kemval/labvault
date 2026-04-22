"""
seed.py — LabVault FDA data seeder
Pulls 100 real drug recall records from the openFDA API and
populates the samples + test_results tables with realistic lab data.
Run automatically on first launch from app.py.
"""

import requests
import random
import string
from datetime import datetime, timedelta
from db import get_conn, insert_sample, insert_test_result, log_action, get_lab_techs

# The openFDA drug enforcement endpoint — completely free, no API key needed.
# It returns real recall records filed with the FDA. Pretty incredible that
# this data is just publicly available.
FDA_URL = "https://api.fda.gov/drug/enforcement.json"

# ─────────────────────────────────────────────
# MAPPINGS — translate FDA fields to LabVault
# ─────────────────────────────────────────────

# FDA uses Class I/II/III to describe recall severity. We map those to
# our own priority labels so the UI stays consistent across FDA imports
# and manually registered samples.
CLASS_TO_PRIORITY = {
    "Class I":   "Critical",   # life-threatening or serious adverse health consequences
    "Class II":  "Major",      # may cause temporary adverse health effects
    "Class III": "Minor",      # unlikely to cause any adverse health consequences
}

# FDA's recall status labels don't match our workflow states, so we translate.
# "Terminated" means the recall process officially ended — we treat that as Completed.
STATUS_MAP = {
    "Ongoing":    "In Progress",
    "Completed":  "Completed",
    "Terminated": "Completed",
}

# ─────────────────────────────────────────────
# SAMPLE TYPE DETECTION — from product description
# ─────────────────────────────────────────────

def detect_sample_type(description: str) -> str:
    """
    Try to figure out what kind of pharmaceutical product this is
    by scanning the product description for keywords.
    The order matters — we check more specific terms first so we don't
    misclassify an "injectable solution" as just a "Liquid".
    Falls back to Tablet since that's by far the most common dosage form.
    """
    desc = description.lower()
    if any(x in desc for x in ["tablet", "tab "]):
        return "Tablet"
    if any(x in desc for x in ["capsule", "cap "]):
        return "Capsule"
    if any(x in desc for x in ["injection", "injectable", "vial", "iv ", "infusion"]):
        return "Injectable"
    if any(x in desc for x in ["solution", "liquid", "syrup", "suspension", "oral solution"]):
        return "Liquid"
    if any(x in desc for x in ["cream", "ointment", "gel", "topical"]):
        return "Topical"
    if any(x in desc for x in ["powder", "granule"]):
        return "Powder"
    return "Tablet"  # default — most common dosage form in practice


# ─────────────────────────────────────────────
# TEST RESULT SIMULATION
# Based on real GxP specifications per USP/ICH guidelines
# ─────────────────────────────────────────────

def simulate_test_results(sample_id: str, reason: str, sample_type: str,
                          tested_by: str, base_date: str) -> list:
    """
    Generate scientifically realistic test results based on the FDA recall reason.
    The idea is that the recall reason tells us *why* the product failed, so we can
    simulate the corresponding lab test result that would have caught it.

    For example: a "dissolution failure" recall → we generate a dissolution result
    that's below the 80% spec. A "superpotency" recall → we generate a potency
    result above 110%. This makes the data feel real and internally consistent.

    OOS = Out Of Specification. Any result outside the spec range gets flagged as Fail (OOS).
    """
    reason_lower = reason.lower()
    results = []
    tested_at = base_date

    def rnd_date(base):
        """Spread test dates across a few days after collection — mimics real lab scheduling."""
        d = datetime.strptime(base, "%Y-%m-%d") + timedelta(days=random.randint(1, 5))
        return d.strftime("%Y-%m-%d")

    # ── DISSOLUTION ──────────────────────────────────────────
    # If the recall mentions dissolution/release problems, simulate a low result.
    # USP spec: ≥80% drug released at 60 min (Q=80%). Our OOS range: 42–74%.
    if any(x in reason_lower for x in ["dissolution", "release", "disintegrat"]):
        value = round(random.uniform(42.0, 74.0), 1)   # OOS — spec ≥80%
        results.append({
            "sample_id": sample_id, "test_name": "Dissolution (60 min)",
            "result_value": value, "result_unit": "%",
            "spec_min": 80.0, "spec_max": None,
            "status": "Fail (OOS)",
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": f"Failed USP Apparatus II. Result {value}% below Q=80% specification."
        })
        # Add a passing potency to show not everything failed — just dissolution.
        # Real recalls often look like this: one test fails while others are fine.
        pot = round(random.uniform(95.0, 105.0), 1)
        results.append({
            "sample_id": sample_id, "test_name": "Potency (% Label Claim)",
            "result_value": pot, "result_unit": "%",
            "spec_min": 90.0, "spec_max": 110.0,
            "status": "Pass",
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": "Within specification."
        })

    # ── SUPERPOTENCY / HIGH POTENCY ──────────────────────────
    # Drug is too strong — more active ingredient than the label says.
    # This is actually quite dangerous and usually triggers a Class I recall.
    elif any(x in reason_lower for x in ["superpoten", "high poten", "overpoten"]):
        value = round(random.uniform(112.0, 135.0), 1)  # OOS — spec 90–110%
        results.append({
            "sample_id": sample_id, "test_name": "Potency (% Label Claim)",
            "result_value": value, "result_unit": "%",
            "spec_min": 90.0, "spec_max": 110.0,
            "status": "Fail (OOS)",
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": f"Superpotency confirmed. Result {value}% exceeds 110% upper limit."
        })

    # ── SUBPOTENCY / LOW POTENCY ─────────────────────────────
    # Drug is too weak — patients might not get an effective dose.
    # "Out of specification" without a specific direction also lands here.
    elif any(x in reason_lower for x in ["subpoten", "low poten", "underpoten", "out of specification"]):
        value = round(random.uniform(68.0, 88.0), 1)    # OOS — spec 90–110%
        results.append({
            "sample_id": sample_id, "test_name": "Potency (% Label Claim)",
            "result_value": value, "result_unit": "%",
            "spec_min": 90.0, "spec_max": 110.0,
            "status": "Fail (OOS)",
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": f"Subpotency confirmed. Result {value}% below 90% lower limit."
        })

    # ── STERILITY ────────────────────────────────────────────
    # Any measurable microbial count in a sterile product is a failure.
    # Spec is literally 0 CFU/mL — even one colony means the product is compromised.
    elif any(x in reason_lower for x in ["sterility", "sterile", "contamina", "microbial"]):
        value = round(random.uniform(150.0, 800.0), 0)  # OOS — spec: 0 CFU/mL
        results.append({
            "sample_id": sample_id, "test_name": "Sterility / Microbial Count",
            "result_value": value, "result_unit": "CFU/mL",
            "spec_min": 0.0, "spec_max": 0.0,
            "status": "Fail (OOS)",
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": f"Microbial contamination detected: {int(value)} CFU/mL. Sterility failure."
        })

    # ── PARTICULATE / FOREIGN MATTER ─────────────────────────
    # Visible particles in a liquid/injectable product — could be glass shards,
    # rubber fragments, or anything that shouldn't be there. Spec: ≤10/container.
    elif any(x in reason_lower for x in ["particulate", "particle", "foreign", "visible"]):
        value = round(random.uniform(15.0, 85.0), 0)    # OOS — spec ≤10 per container
        results.append({
            "sample_id": sample_id, "test_name": "Visible Particulates",
            "result_value": value, "result_unit": "particles/container",
            "spec_min": 0.0, "spec_max": 10.0,
            "status": "Fail (OOS)",
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": f"Visible particulate matter detected: {int(value)} particles/container."
        })

    # ── pH OUT OF RANGE ──────────────────────────────────────
    # pH problems can happen in both directions — a product might be too
    # acidic (corrosive) or too alkaline. We randomly pick one direction.
    elif any(x in reason_lower for x in ["ph ", "acidity", "alkalin"]):
        if random.random() > 0.5:
            value = round(random.uniform(2.5, 3.8), 2)  # too acidic
        else:
            value = round(random.uniform(8.2, 9.5), 2)  # too alkaline
        results.append({
            "sample_id": sample_id, "test_name": "pH",
            "result_value": value, "result_unit": "pH",
            "spec_min": 4.5, "spec_max": 7.5,
            "status": "Fail (OOS)",
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": f"pH {value} outside specification range 4.5–7.5."
        })

    # ── LABELING / MISLABELING ───────────────────────────────
    # Labeling recalls are interesting — the *product* is usually fine,
    # but the packaging or insert has wrong/missing information. So we generate
    # a passing potency (product OK) and a failing label review (packaging not OK).
    elif any(x in reason_lower for x in ["label", "mislab", "packaging", "insert"]):
        pot = round(random.uniform(92.0, 108.0), 1)     # product itself passes
        results.append({
            "sample_id": sample_id, "test_name": "Potency (% Label Claim)",
            "result_value": pot, "result_unit": "%",
            "spec_min": 90.0, "spec_max": 110.0,
            "status": "Pass",
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": "Product potency within spec. Recall due to labeling deficiency, not product failure."
        })
        results.append({
            "sample_id": sample_id, "test_name": "Label Review",
            "result_value": None, "result_unit": "N/A",
            "spec_min": None, "spec_max": None,
            "status": "Fail (OOS)",
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": "Label deficiency confirmed. Missing or incorrect information identified."
        })

    # ── DEFAULT — general potency test ───────────────────────
    # When the recall reason doesn't match any of the specific patterns above,
    # we fall back to a potency test with a 60% failure rate — because these
    # records are from a recall database, failure is more likely than not.
    else:
        oos = random.random() < 0.6   # 60% chance of failure for unclassified reasons
        if oos:
            value = round(random.uniform(70.0, 88.0), 1)
            status = "Fail (OOS)"
            note = f"Result {value}% below 90% specification."
        else:
            value = round(random.uniform(90.0, 110.0), 1)
            status = "Pass"
            note = "Within specification."
        results.append({
            "sample_id": sample_id, "test_name": "Potency (% Label Claim)",
            "result_value": value, "result_unit": "%",
            "spec_min": 90.0, "spec_max": 110.0,
            "status": status,
            "tested_by": tested_by, "tested_at": rnd_date(tested_at),
            "notes": note
        })

    return results


# ─────────────────────────────────────────────
# LOT NUMBER GENERATOR
# ─────────────────────────────────────────────

def fake_lot():
    """
    Generate a realistic-looking pharmaceutical lot number.
    Format: 2 uppercase letters + 4 digits, e.g. "AB1234" or "XK9021".
    FDA records don't always include lot numbers, so we fabricate plausible ones.
    """
    letters = "".join(random.choices(string.ascii_uppercase, k=2))
    numbers = "".join(random.choices(string.digits, k=4))
    return f"{letters}{numbers}"


# ─────────────────────────────────────────────
# MAIN SEED FUNCTION
# ─────────────────────────────────────────────

def seed_from_fda(limit: int = 100) -> dict:
    """
    Fetch real FDA drug recall records and insert them as samples + test results.

    The big design decision here was to do everything in TWO phases:
      Phase 1 — parse all the FDA records in pure Python (no DB calls)
      Phase 2 — one bulk transaction to write everything at once

    Why? Because opening and closing the DB 200 times (100 samples × 2 inserts each)
    is painfully slow. A single executemany() with all rows is orders of magnitude faster.
    We even log the audit entry as a single summary row rather than 100 individual ones.

    Returns a dict with success=True/False, count of records imported, and any error.
    """
    # Get the list of lab techs from the DB so we can randomly assign samples.
    # Fall back to hardcoded names just in case the DB is somehow empty.
    techs = get_lab_techs()
    if not techs:
        techs = ["kembly", "carlos", "maria"]

    params = {
        "limit": limit,
        # Random offset so each import gives a different set of records — more variety
        "skip": random.randint(0, 500),
    }

    # Hit the FDA API — timeout after 15 seconds so we don't hang forever
    try:
        resp = requests.get(FDA_URL, params=params, timeout=15)
        resp.raise_for_status()  # raises an exception for 4xx/5xx responses
        records = resp.json().get("results", [])
    except Exception as e:
        return {"success": False, "error": str(e), "count": 0}

    # ── Phase 1: parse all records in memory ─────────────────
    # Build up two lists (samples, results) without touching the DB yet.
    samples_to_insert = []
    results_to_insert = []
    skipped = 0  # count records we couldn't parse — usually missing sample_id

    for rec in records:
        try:
            sample_id       = rec.get("recall_number", "")[:30]
            product_desc    = rec.get("product_description", "Unknown Product")[:200]
            manufacturer    = rec.get("recalling_firm", "Unknown")[:100]
            reason          = rec.get("reason_for_recall", "Not specified")[:300]
            recall_class    = rec.get("classification", "Class II")
            raw_status      = rec.get("status", "Ongoing")
            init_date       = rec.get("recall_initiation_date", "20240101")[:10]

            # Without a recall number we can't create a unique sample_id — skip it
            if not sample_id:
                skipped += 1
                continue

            # FDA dates come in YYYYMMDD format — convert to YYYY-MM-DD
            try:
                collection_date = datetime.strptime(init_date, "%Y%m%d").strftime("%Y-%m-%d")
            except Exception:
                # If the date is malformed for some reason, just use today
                collection_date = datetime.now().strftime("%Y-%m-%d")

            # Product descriptions can be very long — take just the first sentence
            # and cap at 100 chars so it fits nicely in the UI cards
            product_name = product_desc.split(".")[0][:100].strip()

            sample_type = detect_sample_type(product_desc)
            priority    = CLASS_TO_PRIORITY.get(recall_class, "Major")
            status      = STATUS_MAP.get(raw_status, "Pending")
            assigned_to = random.choice(techs)  # random assignment for demo realism

            samples_to_insert.append({
                "sample_id":         sample_id,
                "product_name":      product_name,
                "lot_number":        fake_lot(),
                "manufacturer":      manufacturer,
                "sample_type":       sample_type,
                "recall_class":      recall_class,
                "priority":          priority,
                "reason_for_recall": reason[:300],
                "collection_date":   collection_date,
                "status":            status,
                "assigned_to":       assigned_to,
                "protocol_id":       None,  # not auto-assigned — lab tech picks the protocol
                "notes":             f"Imported from FDA Recall Enterprise System. Original status: {raw_status}.",
                "source":            "FDA",
            })

            # Simulate test results entirely in Python — no DB hit yet
            results_to_insert.extend(simulate_test_results(
                sample_id   = sample_id,
                reason      = reason,
                sample_type = sample_type,
                tested_by   = assigned_to,
                base_date   = collection_date,
            ))

        except Exception:
            # If any individual record blows up, skip it and keep going —
            # don't let one bad record abort the whole import
            skipped += 1
            continue

    if not samples_to_insert:
        # Nothing to insert (maybe all records were malformed) — still a "success"
        return {"success": True, "count": 0, "skipped": skipped, "error": None}

    # ── Phase 2: one bulk transaction — single DB open/close ──
    # executemany() is dramatically faster than calling execute() in a loop.
    # All 100 samples + their results go in one atomic transaction.
    conn = get_conn()
    try:
        conn.executemany("""
            INSERT OR IGNORE INTO samples
                (sample_id, product_name, lot_number, manufacturer, sample_type,
                 recall_class, priority, reason_for_recall, collection_date,
                 status, assigned_to, protocol_id, notes, source)
            VALUES
                (:sample_id, :product_name, :lot_number, :manufacturer, :sample_type,
                 :recall_class, :priority, :reason_for_recall, :collection_date,
                 :status, :assigned_to, :protocol_id, :notes, :source)
        """, samples_to_insert)

        if results_to_insert:
            conn.executemany("""
                INSERT INTO test_results
                    (sample_id, test_name, result_value, result_unit,
                     spec_min, spec_max, status, tested_by, tested_at, notes)
                VALUES
                    (:sample_id, :test_name, :result_value, :result_unit,
                     :spec_min, :spec_max, :status, :tested_by, :tested_at, :notes)
            """, results_to_insert)

        # One summary audit entry instead of one per record — 100 individual
        # entries would flood the audit trail and make it unreadable.
        conn.execute("""
            INSERT INTO audit_trail (timestamp, user, action, module, target_id, detail)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "system", "SAMPLE_IMPORTED", "FDA Seed", "bulk",
            f"Bulk imported {len(samples_to_insert)} FDA recall records "
            f"with {len(results_to_insert)} test results ({skipped} skipped)."
        ))

        conn.commit()
    finally:
        # Always close the connection — even if something explodes above
        conn.close()
    # ─────────────────────────────────────────────────────────

    return {
        "success": True,
        "count":   len(samples_to_insert),
        "skipped": skipped,
        "error":   None,
    }
