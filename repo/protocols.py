"""
repo/protocols.py — test protocols, including the default GxP set.
"""

from datetime import datetime

from domain import SYSTEM_USER
from repo.core import get_conn, run_in


def insert_protocol(data: dict, conn=None) -> int:
    """
    Insert a protocol; returns its id. Pass `conn` to join the caller's
    transaction. App code should use services.create_protocol.
    """
    def run(c):
        return c.execute("""
            INSERT INTO protocols
                (name, sample_type, description, steps, created_by, created_at)
            VALUES
                (:name, :sample_type, :description, :steps, :created_by, :created_at)
        """, data).lastrowid

    return run_in(conn, run)


def all_protocols():
    """
    Fetch all protocols, newest first.
    """
    conn = get_conn()
    rows = conn.execute("SELECT * FROM protocols ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_protocol(protocol_id: int):
    """Look up a single protocol by ID."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM protocols WHERE id = ?", (protocol_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def seed_protocols():
    """
    Pre-load standard GxP test protocols used in pharmaceutical QC labs.
    These are based on real USP/ICH guidelines — Dissolution, Potency, Sterility, pH, Microbial.
    Runs only once: if the protocols table already has rows, we skip entirely.
    """
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM protocols").fetchone()[0]
    if count > 0:
        conn.close()
        return  # already seeded, nothing to do

    protocols = [
        {
            "name": "Dissolution Testing — USP Apparatus II",
            "sample_type": "Tablet",
            # This test is mandatory for all solid oral dosage forms — it tells us
            # whether the drug actually dissolves and can be absorbed by the body.
            "description": "Measures the rate and extent of drug release from solid oral dosage forms. Required for all solid oral products per USP <711>.",
            "steps": "\n".join([
                "1. Prepare dissolution medium (900 mL of 0.1N HCl or pH 6.8 buffer) at 37°C ± 0.5°C",
                "2. Set paddle speed to 50 RPM",
                "3. Place one tablet per vessel",
                "4. Collect samples at 15, 30, 45, and 60 minutes",
                "5. Filter samples through 0.45 µm membrane filter",
                "6. Analyze by UV spectrophotometry or HPLC",
                "7. Calculate % drug released at each time point",
                "8. Accept if ≥80% released at 60 minutes (Q = 80%)",
                "9. Document all results in the test result log",
            ]),
            "created_by": SYSTEM_USER,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "name": "Potency Assay — HPLC Method",
            "sample_type": "Tablet",
            # HPLC (High-Performance Liquid Chromatography) is the gold standard
            # for measuring how much active ingredient is actually in the pill.
            "description": "Determines the amount of active pharmaceutical ingredient (API) present in the sample. Acceptance: 90.0%–110.0% of label claim.",
            "steps": "\n".join([
                "1. Prepare reference standard solution at known concentration",
                "2. Prepare sample: weigh 20 tablets, calculate average weight",
                "3. Dissolve equivalent of one tablet weight in diluent",
                "4. Sonicate for 15 minutes, filter through 0.22 µm filter",
                "5. Inject standard and sample solutions into HPLC system",
                "6. Column: C18, 150mm x 4.6mm, 5µm particle size",
                "7. Mobile phase: Acetonitrile:Buffer (40:60)",
                "8. Flow rate: 1.0 mL/min, UV detection at 254 nm",
                "9. Calculate % label claim from peak areas",
                "10. Accept if result is 90.0%–110.0%",
            ]),
            "created_by": SYSTEM_USER,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "name": "Sterility Testing — Membrane Filtration",
            "sample_type": "Injectable",
            # For injectables, any microbial contamination can be life-threatening —
            # hence the 14-day incubation period to catch slow-growing organisms.
            "description": "Verifies absence of viable microorganisms in sterile pharmaceutical products per USP <71>.",
            "steps": "\n".join([
                "1. Perform all testing in ISO Class 5 laminar flow hood",
                "2. Prepare culture media: Fluid Thioglycollate (FTM) and Soybean Casein Digest (SCDB)",
                "3. Filter entire sample volume through 0.45 µm membrane",
                "4. Transfer membrane to both FTM and SCDB media",
                "5. Incubate FTM at 30–35°C for 14 days",
                "6. Incubate SCDB at 20–25°C for 14 days",
                "7. Inspect daily for turbidity or microbial growth",
                "8. Accept if no growth observed at 14 days",
                "9. If growth observed: invalidate or fail — initiate deviation report",
            ]),
            "created_by": SYSTEM_USER,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "name": "pH Measurement — USP <791>",
            "sample_type": "Liquid",
            # pH affects everything: drug stability, patient comfort, absorption rate.
            # Even a small drift outside spec can compromise the product.
            "description": "Determines pH of liquid pharmaceutical preparations. Critical for product stability, efficacy, and patient safety.",
            "steps": "\n".join([
                "1. Calibrate pH meter with two buffer solutions bracketing expected sample pH",
                "2. Rinse electrode with purified water, blot dry",
                "3. Immerse electrode in sample at room temperature (20–25°C)",
                "4. Allow reading to stabilize (minimum 30 seconds)",
                "5. Record pH to two decimal places",
                "6. Rinse electrode, repeat measurement — values must agree within ±0.05",
                "7. Report mean of two readings",
                "8. Compare to specification range in product monograph",
            ]),
            "created_by": SYSTEM_USER,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "name": "Microbial Limits Testing — USP <61>/<62>",
            "sample_type": "Non-sterile",
            # Non-sterile products (like oral tablets) aren't required to be
            # completely free of microbes — but they still have limits.
            # TAMC and TYMC are the standard counts pharma labs track.
            "description": "Determines total aerobic microbial count (TAMC) and total yeast/mold count (TYMC) in non-sterile products.",
            "steps": "\n".join([
                "1. Prepare sample: dissolve/dilute in buffered sodium chloride-peptone solution",
                "2. Perform serial 10-fold dilutions as needed",
                "3. TAMC: plate on Soybean Casein Digest Agar, incubate 30–35°C for 5 days",
                "4. TYMC: plate on Sabouraud Dextrose Agar, incubate 20–25°C for 5 days",
                "5. Count colonies after incubation",
                "6. Calculate CFU/g or CFU/mL",
                "7. Accept TAMC ≤ 1000 CFU/g (oral), TYMC ≤ 100 CFU/g (oral)",
                "8. Check for absence of specified microorganisms (E. coli, Salmonella)",
                "9. Document all plate counts and calculations",
            ]),
            "created_by": SYSTEM_USER,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    ]

    for p in protocols:
        conn.execute("""
            INSERT INTO protocols (name, sample_type, description, steps, created_by, created_at)
            VALUES (:name, :sample_type, :description, :steps, :created_by, :created_at)
        """, p)

    conn.commit()
    conn.close()
