"""
views/navigation.py — the app's pages, defined once (ADR 0018).

app.py registers them with st.navigation. Each view file is a Streamlit page:
it runs show() when executed as the page script. Icons are Material Symbols,
which Streamlit renders aria-hidden, so screen readers announce only the
title (audit U5); emoji in labels were read aloud.
"""

from domain import ROLE_ADMIN

# (title, view file relative to app.py, icon, admin only)
PAGES = [
    ("Dashboard",          "views/dashboard.py",       ":material/dashboard:",            False),
    ("Sample Intake",      "views/sample_intake.py",   ":material/add_box:",              False),
    ("Sample Tracking",    "views/sample_tracking.py", ":material/biotech:",              False),
    ("Test Results",       "views/test_results.py",    ":material/science:",              False),
    ("OOS Investigations", "views/investigations.py",  ":material/report:",               False),
    ("Protocols",          "views/protocols.py",       ":material/description:",          False),
    ("Specifications",     "views/specifications.py",  ":material/straighten:",           False),
    ("Reports",            "views/reports.py",         ":material/bar_chart:",            False),
    ("Audit Trail",        "views/audit_trail.py",     ":material/history:",              False),
    ("Admin",              "views/admin.py",           ":material/admin_panel_settings:", True),
    ("My Account",         "views/account.py",         ":material/account_circle:",       False),
]


def pages_for(role):
    """The pages `role` may open. An admin-only page isn't registered for
    anyone else, so its URL doesn't resolve for them (the view re-checks too)."""
    return [p for p in PAGES if role == ROLE_ADMIN or not p[3]]
