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
from db import insert_sample, insert_test_result, log_action, get_lab_techs

FDA_URL = "https://api.fda.gov/drug/enforcement.json"

# ─────────────────────────────────────────────
# MAPPINGS — translate FDA fields to LabVault
# ─────────────────────────────────────────────

CLASS_TO_PRIORITY = {
    "Class I":   "Critical",   # life-threatening
    "Class II":  "Major",      # temporary adverse health
    "Class III": "Minor",      # unlikely to cause harm
}

STATUS_MAP = {
    "Ongoing":    "In Progress",
    "Completed":  "Completed",
    "Terminated": "Completed",
}

# ─────────────────────────────────────────────
# SAMPLE TYPE DETECTION — from product description
# ─────────────────────────────────────────────

def detect_sample_type(description: str) -> str:
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
    return "Tablet"  # default — most common dosage form


# ─────────────────────────────────────────────
# TEST RESULT SIMULATION
# Based on real GxP specifications per USP/ICH guidelines
# ─────────────────────────────────────────────

def simulate_test_results(sample_id: str, reason: str, sample_type: str,
                          tested_by: str, base_date: str) -> list:
    """
    Generate scientifically realistic test results based on the
    FDA recall reason. OOS results are grounded in the actual failure.
    """
    reason_lower = reason.lower()
    results = []
    tested_at = base_date

    def rnd_date(base):
        d = datetime.strptime(base, "%Y-%m-%d") + timedelta(days=random.randint(1, 5))
        return d.strftime("%Y-%m-%d")

    # ── DISSOLUTION ──────────────────────────────────────────
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
        # Add a passing potency to show not everything failed
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
    elif any(x in reason_lower for x in ["ph ", "acidity", "alkalin"]):
        # randomly pick too high or too low
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
    else:
        oos = random.random() < 0.6   # 60% fail for unknown reasons
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
    letters = "".join(random.choices(string.ascii_uppercase, k=2))
    numbers = "".join(random.choices(string.digits, k=4))
    return f"{letters}{numbers}"


# ─────────────────────────────────────────────
# MAIN SEED FUNCTION
# ─────────────────────────────────────────────

def seed_from_fda(limit: int = 100) -> dict:
    """
    Fetch real FDA drug recall records and insert them as samples.
    Returns a summary dict for display in the UI.
    """
    techs = get_lab_techs()
    if not techs:
        techs = ["kembly", "carlos", "maria"]

    params = {
        "limit": limit,
        "skip": random.randint(0, 500),   # random offset for variety
    }

    try:
        resp = requests.get(FDA_URL, params=params, timeout=15)
        resp.raise_for_status()
        records = resp.json().get("results", [])
    except Exception as e:
        return {"success": False, "error": str(e), "count": 0}

    inserted = 0
    skipped = 0

    for rec in records:
        try:
            sample_id       = rec.get("recall_number", "")[:30]
            product_desc    = rec.get("product_description", "Unknown Product")[:200]
            manufacturer    = rec.get("recalling_firm", "Unknown")[:100]
            reason          = rec.get("reason_for_recall", "Not specified")[:300]
            recall_class    = rec.get("classification", "Class II")
            raw_status      = rec.get("status", "Ongoing")
            init_date       = rec.get("recall_initiation_date", "20240101")[:10]

            if not sample_id:
                skipped += 1
                continue

            # Clean up date format
            try:
                collection_date = datetime.strptime(init_date, "%Y%m%d").strftime("%Y-%m-%d")
            except Exception:
                collection_date = datetime.now().strftime("%Y-%m-%d")

            # Shorten product name for display (keep first sentence / 100 chars)
            product_name = product_desc.split(".")[0][:100].strip()

            sample_type = detect_sample_type(product_desc)
            priority    = CLASS_TO_PRIORITY.get(recall_class, "Major")
            status      = STATUS_MAP.get(raw_status, "Pending")
            assigned_to = random.choice(techs)

            sample_data = {
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
                "protocol_id":       None,
                "notes":             f"Imported from FDA Recall Enterprise System. Original status: {raw_status}.",
                "source":            "FDA",
            }

            insert_sample(sample_data)

            # Simulate test results for this sample
            test_results = simulate_test_results(
                sample_id   = sample_id,
                reason      = reason,
                sample_type = sample_type,
                tested_by   = assigned_to,
                base_date   = collection_date,
            )
            for tr in test_results:
                insert_test_result(tr)

            log_action(
                user      = "system",
                action    = "SAMPLE_IMPORTED",
                module    = "FDA Seed",
                target_id = sample_id,
                detail    = f"Imported: {product_name} | {manufacturer} | {recall_class}"
            )

            inserted += 1

        except Exception:
            skipped += 1
            continue

    return {
        "success": True,
        "count":   inserted,
        "skipped": skipped,
        "error":   None,
    }
