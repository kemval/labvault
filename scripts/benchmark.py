"""
Page render benchmark (roadmap 4.2, ADR 0020).

Builds a throwaway database with N samples (default 10,000), about 1.2 test
results each, OOS investigations, signatures and audit rows, then renders
every page through the real app (Streamlit AppTest) and prints how long
each took. Never touches ./labvault.db.

    .venv/bin/python scripts/benchmark.py [--samples 10000] [--budget 1.0]

Exits non-zero if any page takes longer than --budget seconds.
Timings are for a cold cache (first render after the data changed), which
is what a user sees after any write.
"""

import argparse
import os
import random
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASSWORD = "bench-password-1"


def build(db_path: str, n_samples: int, seed: int = 7) -> dict:
    """Fill `db_path` with n_samples and related rows; returns row counts."""
    from domain import (CONCLUSION_CONFIRMED, CONCLUSION_LAB_ERROR, PRIORITIES, RESULT_OOS,
                        RESULT_PASS, SAMPLE_STATUSES)
    from repo import core, passwords, schema

    core.DB_PATH = db_path
    schema.init_db()
    rnd = random.Random(seed)
    techs = [f"tech{i}" for i in range(8)]
    pw = passwords.hash_password(PASSWORD)
    with core.transaction() as conn:
        conn.executemany("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                         [("admin", pw, "admin"), *[(t, pw, "lab_tech") for t in techs]])
        samples = []
        for i in range(n_samples):
            status = rnd.choices(SAMPLE_STATUSES, weights=(2, 3, 4, 1))[0]
            samples.append((f"B-{i:06d}", f"Product {i} tablets 500 mg", f"L{i}", "Acme",
                            "Tablet", "Class II", rnd.choice(PRIORITIES), "Bench",
                            f"2025-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}", status,
                            rnd.choice(techs + [None]), None, "", "Manual"))
        conn.executemany("""
            INSERT INTO samples (sample_id, product_name, lot_number, manufacturer,
                sample_type, recall_class, priority, reason_for_recall, collection_date,
                status, assigned_to, protocol_id, notes, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", samples)

        results = []
        for sid, *_rest in samples:
            for _ in range(rnd.choice((0, 1, 1, 1, 2, 2))):
                value = rnd.uniform(85, 112)
                status = RESULT_OOS if not 90 <= value <= 110 else RESULT_PASS
                results.append((sid, "Potency (% Label Claim)", round(value, 1), "%", 90.0,
                                110.0, status, rnd.choice(techs),
                                f"2025-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}", ""))
        conn.executemany("""
            INSERT INTO test_results (sample_id, test_name, result_value, result_unit,
                spec_min, spec_max, status, tested_by, tested_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", results)

        rows = conn.execute("SELECT id, status, tested_by FROM test_results").fetchall()
        for rid, status, analyst in rows:
            if status == RESULT_OOS:
                closed = rnd.random() < 0.5
                conclusion = rnd.choice((CONCLUSION_CONFIRMED, CONCLUSION_LAB_ERROR))
                conn.execute(
                    "INSERT INTO oos_investigations (result_id, opened_by, opened_at, status, "
                    "conclusion, findings, closed_by, closed_at) VALUES (?, 'system', "
                    "'2025-06-01T00:00:00Z', ?, ?, ?, ?, ?)",
                    (rid, "Closed" if closed else "Open", conclusion if closed else None,
                     "Bench findings" if closed else None, "admin" if closed else None,
                     "2025-06-02T00:00:00Z" if closed else None))
                if closed:
                    meaning = "Rejected" if conclusion == CONCLUSION_LAB_ERROR else "Approved"
                    conn.execute("INSERT INTO result_signatures (result_id, signed_by, meaning, "
                                 "reason) VALUES (?, 'admin', ?, ?)",
                                 (rid, meaning, "lab error" if meaning == "Rejected" else None))
            elif rnd.random() < 0.6:
                conn.execute("INSERT INTO result_signatures (result_id, signed_by, meaning) "
                             "VALUES (?, ?, 'Approved')",
                             (rid, "admin" if analyst != "admin" else techs[0]))
        conn.executemany(
            "INSERT INTO audit_trail (timestamp, user, action, module, target_id, detail) "
            "VALUES ('2025-06-01T00:00:00Z', 'system', 'SAMPLE_IMPORTED', 'Bench', ?, 'bench')",
            [(s[0],) for s in samples])
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("samples", "test_results", "oos_investigations",
                            "result_signatures", "audit_trail")}
    return counts


def time_pages(username: str = "admin") -> dict:
    """Seconds to render each page from a cold cache, signed in as `username`."""
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from views.navigation import PAGES

    os.environ["LABVAULT_DEMO_MODE"] = "true"
    import services
    services.import_fda = lambda **_: {"success": False, "error": "offline", "count": 0}

    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120)
    at.run()
    at.text_input[0].input(username)
    at.text_input[1].input(PASSWORD)
    at.button[0].click().run()
    assert at.session_state.logged_in, "benchmark sign-in failed"

    timings = {}
    for title, path, _icon, admin_only in PAGES:
        if admin_only and username != "admin":
            continue
        st.cache_data.clear()                 # cold: as after any write
        at.switch_page(path)
        started = time.perf_counter()
        at.run()
        timings[title] = time.perf_counter() - started
        if at.exception:
            raise RuntimeError(f"{title}: {at.exception}")
    return timings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--samples", type=int, default=10_000)
    parser.add_argument("--budget", type=float, default=1.0, help="seconds per page")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        counts = build(os.path.join(tmp, "bench.db"), args.samples)
        print("Data:", ", ".join(f"{v:,} {k}" for k, v in counts.items()))
        timings = time_pages()
        slow = {t: s for t, s in timings.items() if s > args.budget}
        for title, seconds in sorted(timings.items(), key=lambda kv: -kv[1]):
            print(f"  {title:<20} {seconds * 1000:8.0f} ms{'  SLOW' if title in slow else ''}")
        print(f"Budget {args.budget:.1f} s per page: "
              f"{'all pages within budget' if not slow else f'{len(slow)} over budget'}")
        return 1 if slow else 0


if __name__ == "__main__":
    sys.exit(main())
