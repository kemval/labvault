"""Layering rules from ADR 0006, enforced."""
import os
import re
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_repo_seed_and_scripts_run_without_streamlit(tmp_path):
    # A fresh interpreter: init a DB, run migrations (which import seed),
    # seed users and protocols, write an FDA batch, back it up — then check
    # that Streamlit was never imported.
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {ROOT!r})
        from repo import core, schema, users, protocols, samples, fda_import
        import seed
        from scripts import backup_db, dedupe_simulated_results  # noqa: F401
        core.DB_PATH = {str(tmp_path / "t.db")!r}
        schema.init_db()
        users.seed_users(demo=True)
        protocols.seed_protocols()
        rec = {{"recall_number": "D-1", "product_description": "X Tablets", "recalling_firm": "F",
               "reason_for_recall": "subpotent", "classification": "Class I",
               "status": "Ongoing", "recall_initiation_date": "20240101"}}
        parsed, skipped = seed.parse_records([rec], users.lab_techs())
        assert fda_import.write_batch(parsed, skipped)["count"] == 1
        assert samples.sample_exists()
        backup_db.backup_database(core.DB_PATH)
        assert "streamlit" not in sys.modules, "streamlit was imported"
        print("ok")
    """)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stderr


def test_views_never_write_sql():
    write_sql = re.compile(r"\b(INSERT|UPDATE|DELETE)\s+(INTO|FROM|\w+\s+SET)\b", re.IGNORECASE)
    views = os.path.join(ROOT, "views")
    offenders = [name for name in os.listdir(views) if name.endswith(".py")
                 and write_sql.search(open(os.path.join(views, name), encoding="utf-8").read())]
    assert offenders == []
