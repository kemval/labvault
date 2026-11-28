"""
app.py — LabVault main entry point
Handles login, session state, navigation, and first-run database seeding.
Run with: streamlit run app.py
"""

import importlib
import time

import streamlit as st
from domain import (LOCKOUT_MINUTES, MAX_FAILED_LOGINS, ROLE_ADMIN, ROLE_LAB_TECH,
                    SESSION_IDLE_MINUTES)
from config import ConfigError, demo_mode, admin_password
from db import sample_exists, count_simulated, clear_user_caches
from repo.protocols import seed_protocols
from repo.specifications import seed_specifications
from repo.schema import init_db
from repo.users import DEMO_USERS, seed_users, session_account
import services

# ─────────────────────────────────────────────
# PAGE CONFIG — must be first Streamlit call
# ─────────────────────────────────────────────

# This MUST come before anything else that touches Streamlit — if you put
# any st.* call above this, Streamlit throws a fit and refuses to run.
st.set_page_config(
    page_title="LabVault",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# GLOBAL STYLES
# ─────────────────────────────────────────────

# Injecting raw CSS into the Streamlit app. It feels a bit hacky, but it's
# actually the recommended pattern — Streamlit gives us this escape hatch
# via unsafe_allow_html so we can add custom styles without fighting the
# default theme too hard.
st.markdown("""
<style>
    /* Sidebar — deep navy background so it feels like a proper app, not a prototype */
    [data-testid="stSidebar"] {
        background-color: #0f2942;
    }
    [data-testid="stSidebar"] * {
        color: #e8f0fe !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        font-size: 15px;
        padding: 6px 0;
    }

    /* Top header bar — gradient from dark navy to a slightly lighter blue.
       The 90deg angle gives it a clean left-to-right sweep. */
    .lv-header {
        background: linear-gradient(90deg, #0f2942 0%, #1a4a8a 100%);
        color: white;
        padding: 18px 28px;
        border-radius: 10px;
        margin-bottom: 24px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .lv-header h1 {
        margin: 0;
        font-size: 38px;
        font-weight: 700;
        letter-spacing: 1px;
    }
    .lv-header span {
        font-size: 16px;
        opacity: 0.75;   /* subtle — it's a subtitle, not a headline */
    }

    /* Metric cards — the colored left border is a quick visual cue for severity */
    .metric-card {
        background: white;
        border-radius: 10px;
        padding: 20px;
        border-left: 5px solid #1a4a8a;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    .metric-card.critical { border-left-color: #d32f2f; }  /* red = critical */
    .metric-card.warning  { border-left-color: #f57c00; }  /* orange = warning */
    .metric-card.success  { border-left-color: #2e7d32; }  /* green = all good */

    /* Status badges — pill-shaped tags for at-a-glance sample status */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    /* Each badge pair uses a very light background with a saturated text color —
       high contrast without being visually overwhelming */
    .badge-pending    { background:#fff3e0; color:#e65100; }
    .badge-progress   { background:#e3f2fd; color:#1565c0; }
    .badge-completed  { background:#e8f5e9; color:#2e7d32; }
    .badge-rejected   { background:#fce4ec; color:#c62828; }
    .badge-pass       { background:#e8f5e9; color:#2e7d32; }
    .badge-fail       { background:#fce4ec; color:#c62828; }
    .badge-critical   { background:#fce4ec; color:#c62828; }
    .badge-major      { background:#fff3e0; color:#e65100; }
    .badge-minor      { background:#e8f5e9; color:#2e7d32; }
    .badge-sim        { background:#ede7f6; color:#4527a0; }  /* demo data marker */

    /* Login box — centered card that floats in the middle of the page.
       The shadow gives it depth so it doesn't feel flat. */
    .login-container {
        max-width: 420px;
        margin: 80px auto;
        padding: 40px;
        background: white;
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.12);
        text-align: center;
    }
    .login-logo {
        font-size: 52px;
        margin-bottom: 8px;
    }
    .login-title {
        font-size: 28px;
        font-weight: 800;
        color: #0f2942;
        margin-bottom: 4px;
    }
    .login-subtitle {
        color: #666;
        font-size: 13px;
        margin-bottom: 28px;
    }

    /* Hide Streamlit default elements (keep header so sidebar toggle works)
       The main menu and footer are just noise — hiding them keeps things clean.
       The header itself stays because it has the sidebar collapse button. */
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    header[data-testid="stHeader"] {
        background: transparent !important;
        backdrop-filter: none !important;
    }
    /* This was a tricky one — on Streamlit Cloud the sidebar toggle would
       sometimes vanish. Force-showing it with z-index ensures it stays
       clickable no matter what other styles try to hide it. */
    button[data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"] {
        visibility: visible !important;
        opacity: 1 !important;
        z-index: 999 !important;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# FIRST-RUN SETUP
# ─────────────────────────────────────────────

# @st.cache_resource runs this once per server process (shared by every
# session), so init_db() and seeding happen once, not on every rerun.
# If setup raises, nothing is cached and the next run tries again.
@st.cache_resource(show_spinner=False)
def setup():
    """Initialize DB and seed data once per server process."""
    init_db()        # creates all tables and indexes if they don't exist yet
    seed_users(demo=demo_mode(), admin_password=admin_password())
    seed_protocols() # loads the standard GxP protocols (Dissolution, Potency, etc.)
    if demo_mode():
        # Acceptance limits are a QA decision: only demo instances get defaults.
        seed_specifications()
    clear_user_caches()
    return True

try:
    setup()
except ConfigError as e:
    st.error(f"LabVault is not configured correctly: {e}")
    st.stop()


# ─────────────────────────────────────────────
# SESSION STATE DEFAULTS
# ─────────────────────────────────────────────

# Streamlit re-runs the whole script on every interaction, so session_state
# is how we keep things like login status alive between those re-runs.
# We only initialize keys if they don't exist yet — otherwise we'd wipe
# the state on every page interaction, which would be a nightmare.
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"
if "auto_import_attempted" not in st.session_state:
    # The first-login FDA auto-import runs at most once per session —
    # success or failure — so a down API can't block every rerun.
    st.session_state.auto_import_attempted = False


# ─────────────────────────────────────────────
# LOGIN SCREEN
# ─────────────────────────────────────────────

def show_login():
    # The login logo/title is rendered as raw HTML so we can center it
    # the way we want — Streamlit's built-in layout doesn't give us
    # the same level of control for this kind of centered card design.
    st.markdown("""
        <div class="login-container">
            <div class="login-logo">🧪</div>
            <div class="login-title">LabVault</div>
            <div class="login-subtitle">
                Pharmaceutical Lab Management System<br>
                Sample data: real FDA recalls with simulated lab results
            </div>
        </div>
    """, unsafe_allow_html=True)

    # The [1, 1.2, 1] ratio gives us a centered column that's slightly
    # wider than the flanking empty columns — a clean way to center content.
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        if st.session_state.pop("timed_out", False):
            st.info(f"You were signed out after {SESSION_IDLE_MINUTES} minutes without "
                    "activity. Sign in again to continue.")
        if st.session_state.pop("account_disabled", False):
            st.warning("You were signed out because your account was disabled. "
                       "Contact an administrator.")
        st.markdown("#### Sign in to your account")
        username = st.text_input("Username", placeholder="e.g. admin")
        password = st.text_input("Password", type="password", placeholder="••••••••")

        if st.button("Sign In", use_container_width=True, type="primary"):
            # sign_in() checks the hashed password and audits the attempt —
            # returns a user dict on success, None on failure.
            user = services.sign_in(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.session_state.last_activity = time.time()
                st.rerun()   # rerun triggers the main logic to show the app
            else:
                # One message for every failure, so it can't reveal which
                # accounts exist or are locked (ADR 0013).
                st.error(f"Invalid username or password. After {MAX_FAILED_LOGINS} failed "
                         f"attempts an account is locked for {LOCKOUT_MINUTES} minutes.")

        # Demo credentials are public by design, so they are shown only on
        # demo instances — never on a secure deployment.
        if demo_mode():
            st.markdown("---")
            admin_user = next(u for u in DEMO_USERS if u[2] == ROLE_ADMIN)
            tech_user  = next(u for u in DEMO_USERS if u[2] == ROLE_LAB_TECH)
            st.caption(
                f"Demo instance — Admin: `{admin_user[0]}` / `{admin_user[1]}`  |  "
                f"Lab Tech: `{tech_user[0]}` / `{tech_user[1]}`"
            )


# ─────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ─────────────────────────────────────────────

# Navigation: (sidebar label, page name, view module, admin only).
# The single source for both the sidebar and route().
PAGES = [
    ("📊  Dashboard",       "Dashboard",       "views.dashboard",       False),
    ("🧫  Sample Intake",   "Sample Intake",   "views.sample_intake",   False),
    ("🔬  Sample Tracking", "Sample Tracking", "views.sample_tracking", False),
    ("📋  Test Results",    "Test Results",    "views.test_results",    False),
    ("🔎  OOS Investigations", "OOS Investigations", "views.investigations", False),
    ("📄  Protocols",       "Protocols",       "views.protocols",       False),
    ("📏  Specifications",  "Specifications",  "views.specifications",  False),
    ("📈  Reports",         "Reports",         "views.reports",         False),
    ("🕵️  Audit Trail",     "Audit Trail",     "views.audit_trail",     False),
    ("⚙️  Admin",           "Admin",           "views.admin",           True),
    ("🔑  My Account",      "My Account",      "views.account",         False),
]


def show_sidebar():
    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        st.markdown("### 🧪 LabVault")
        # Show the username and role — replace underscores so "lab_tech" reads as "Lab Tech"
        st.markdown(f"**{user['username']}** · *{role.replace('_', ' ').title()}*")
        st.markdown("---")

        # Admin-only pages are hidden from lab techs (each view re-checks the role).
        pages = {label: name for label, name, _, admin_only in PAGES
                 if role == ROLE_ADMIN or not admin_only}
        choice = st.radio("Navigation", list(pages), label_visibility="collapsed")
        st.session_state.page = pages[choice]

        st.markdown("---")

        # FDA data import — only admins should be able to trigger a bulk import
        if role == ROLE_ADMIN:
            st.markdown("**Data Management**")
            if not sample_exists():
                # Let the admin know the DB is empty so they're not confused
                st.warning("No samples yet. Import FDA data.")
            if st.button("🔄 Import FDA Data", use_container_width=True):
                with st.spinner("Fetching real FDA recall records..."):
                    result = services.import_fda(limit=100, user=user["username"])
                if result["success"]:
                    st.success(f"✅ Imported {result['count']} new samples "
                               f"({result['already_present']} already present)")
                    st.rerun()
                else:
                    st.error(f"❌ {result['error']}")
            st.markdown("---")

        # Sign out clears session state and forces a rerun back to the login screen
        sign_out_button()


# ─────────────────────────────────────────────
# PAGE ROUTER
# ─────────────────────────────────────────────

def route():
    """
    Load the view for session_state.page. Views are imported lazily, so only
    the page the user navigates to is loaded.
    """
    module = next(m for _, name, m, _ in PAGES if name == st.session_state.page)
    importlib.import_module(module).show()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def end_idle_session():
    """
    Sign out a session idle for longer than SESSION_IDLE_MINUTES (audit H6).
    Streamlit only reruns on interaction, so this runs on the first action
    after the idle period, which is then refused.
    """
    now = time.time()
    if now - st.session_state.get("last_activity", now) > SESSION_IDLE_MINUTES * 60:
        services.sign_out(st.session_state.user["username"], idle=True)
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.timed_out = True
    st.session_state.last_activity = now


def refresh_account():
    """
    Re-read the signed-in account on every rerun, so an admin disabling it
    or changing its role applies at the user's next click (ADR 0017).
    """
    username = st.session_state.user["username"]
    account = session_account(username)
    if account is None or not account["active"]:
        services.log_event(username, "LOGOUT", "Auth", username,
                           "Signed out: account disabled")
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.account_disabled = True
    else:
        st.session_state.user = account


def sign_out_button():
    if st.button("Sign Out", use_container_width=True):
        services.sign_out(st.session_state.user["username"])
        st.session_state.logged_in = False
        st.session_state.user = None
        st.rerun()


def show_forced_password_change():
    """A password set by an admin must be replaced before anything else."""
    from views.account import password_form
    st.markdown("#### Choose a new password")
    st.info("An administrator set a temporary password for your account. "
            "Choose your own password to continue.")
    password_form(st.session_state.user, forced=True)
    with st.sidebar:
        sign_out_button()


if st.session_state.logged_in:
    end_idle_session()
if st.session_state.logged_in:
    refresh_account()

if not st.session_state.logged_in:
    # Not logged in yet — show the login screen and stop here
    show_login()
elif st.session_state.user["must_change_password"]:
    show_forced_password_change()
else:
    show_sidebar()

    # On the very first login, if the DB is completely empty, kick off
    # the FDA import automatically so the user sees real data right away
    # instead of a blank dashboard. It is attempted once per session; with
    # only_if_empty=True, a session that loses the race to another one's
    # import becomes a no-op instead of importing a second batch.
    if not st.session_state.auto_import_attempted and not sample_exists():
        st.session_state.auto_import_attempted = True
        with st.spinner("🔬 First launch — importing real FDA pharmaceutical data..."):
            result = services.import_fda(limit=100, only_if_empty=True,
                                         user=st.session_state.user["username"])
        if result["success"]:
            st.success(f"✅ {result['count']} real FDA recall records imported. Welcome to LabVault!")
            st.rerun()
        else:
            hint = ("Use **🔄 Import FDA Data** in the sidebar to try again."
                    if st.session_state.user["role"] == ROLE_ADMIN
                    else "Ask an administrator to import the data.")
            st.error(f"Could not import FDA data: {result['error']}. {hint}")

    # Demo data must never be mistaken for real QC records (audit C4).
    simulated = count_simulated()
    if simulated["samples"] or simulated["results"]:
        st.info(
            f"🧪 **Demo data:** {simulated['samples']} samples and {simulated['results']} "
            "test results here are **simulated**: real FDA recall records with invented "
            "lot numbers, assignments and lab results. They are marked **SIMULATED** "
            "and must not be used as real QC data."
        )

    route()
