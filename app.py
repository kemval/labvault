"""
app.py — LabVault main entry point
Handles login, session state, navigation, and first-run database seeding.
Run with: streamlit run app.py
"""

import streamlit as st
from db import init_db, seed_users, seed_protocols, authenticate, sample_exists
from seed import seed_from_fda

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

# @st.cache_resource is perfect here — it runs once per server session and
# caches the result forever. No matter how many times the page reloads,
# init_db() and seeding only happen once. Super efficient.
@st.cache_resource(show_spinner=False)
def setup():
    """Initialize DB and seed data exactly once per session."""
    init_db()        # creates all tables and indexes if they don't exist yet
    seed_users()     # adds default admin + lab tech accounts
    seed_protocols() # loads the standard GxP protocols (Dissolution, Potency, etc.)
    return True

setup()


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
if "fda_seeded" not in st.session_state:
    # Track whether we already imported FDA data this session,
    # so we don't trigger the spinner on every rerun.
    st.session_state.fda_seeded = False


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
                Powered by real FDA recall data
            </div>
        </div>
    """, unsafe_allow_html=True)

    # The [1, 1.2, 1] ratio gives us a centered column that's slightly
    # wider than the flanking empty columns — a clean way to center content.
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("#### Sign in to your account")
        username = st.text_input("Username", placeholder="e.g. admin")
        password = st.text_input("Password", type="password", placeholder="••••••••")

        if st.button("Sign In", use_container_width=True, type="primary"):
            # authenticate() checks the hashed password in the DB —
            # returns a user dict on success, None on failure.
            user = authenticate(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()   # rerun triggers the main logic to show the app
            else:
                st.error("Invalid username or password.")

        st.markdown("---")
        # A small hint for demo purposes — helpful for anyone exploring the app
        st.markdown(
            "<small style='color:#999'>Demo accounts — Admin: `admin` / `admin123` &nbsp;|&nbsp; "
            "Lab Tech: `kembly` / `lab2024`</small>",
            unsafe_allow_html=True
        )


# ─────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ─────────────────────────────────────────────

def show_sidebar():
    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        st.markdown("### 🧪 LabVault")
        # Show the username and role — replace underscores so "lab_tech" reads as "Lab Tech"
        st.markdown(f"**{user['username']}** · *{role.replace('_', ' ').title()}*")
        st.markdown("---")

        # List of navigation pages — emoji prefix is decorative, stripped before routing
        pages = [
            "📊  Dashboard",
            "🧫  Sample Intake",
            "🔬  Sample Tracking",
            "📋  Test Results",
            "📄  Protocols",
            "📈  Reports",
            "🕵️  Audit Trail",
        ]

        # Admin-only page — lab techs don't need to see user management
        if role == "admin":
            pages.append("⚙️  Admin")

        choice = st.radio("Navigation", pages, label_visibility="collapsed")

        # Strip the emoji prefix (and the double-space after it) to get
        # a clean page name like "Dashboard" or "Sample Intake"
        clean = choice.split("  ", 1)[-1].strip()
        st.session_state.page = clean

        st.markdown("---")

        # FDA data import — only admins should be able to trigger a bulk import
        if role == "admin":
            st.markdown("**Data Management**")
            if not sample_exists():
                # Let the admin know the DB is empty so they're not confused
                st.warning("No samples yet. Import FDA data.")
            if st.button("🔄 Import FDA Data", use_container_width=True):
                with st.spinner("Fetching real FDA recall records..."):
                    result = seed_from_fda(limit=100)
                if result["success"]:
                    st.success(f"✅ Imported {result['count']} samples")
                    st.session_state.fda_seeded = True
                    st.rerun()
                else:
                    st.error(f"❌ {result['error']}")
            st.markdown("---")

        # Sign out clears session state and forces a rerun back to the login screen
        if st.button("Sign Out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()


# ─────────────────────────────────────────────
# PAGE ROUTER
# ─────────────────────────────────────────────

def route():
    """
    Looks at session_state.page and loads the matching view module.
    Each view is imported lazily so we don't load everything upfront —
    only the page the user actually navigates to gets imported.
    """
    page = st.session_state.page

    if page == "Dashboard":
        from views.dashboard import show
        show()
    elif page == "Sample Intake":
        from views.sample_intake import show
        show()
    elif page == "Sample Tracking":
        from views.sample_tracking import show
        show()
    elif page == "Test Results":
        from views.test_results import show
        show()
    elif page == "Protocols":
        from views.protocols import show
        show()
    elif page == "Reports":
        from views.reports import show
        show()
    elif page == "Audit Trail":
        from views.audit_trail import show
        show()
    elif page == "Admin":
        from views.admin import show
        show()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if not st.session_state.logged_in:
    # Not logged in yet — show the login screen and stop here
    show_login()
else:
    show_sidebar()

    # On the very first login, if the DB is completely empty, kick off
    # the FDA import automatically so the user sees real data right away
    # instead of a blank dashboard. The fda_seeded flag prevents this
    # from running again on every page navigation within the session.
    if not sample_exists() and not st.session_state.fda_seeded:
        with st.spinner("🔬 First launch — importing real FDA pharmaceutical data..."):
            result = seed_from_fda(limit=100)
        if result["success"]:
            st.session_state.fda_seeded = True
            st.success(f"✅ {result['count']} real FDA recall records imported. Welcome to LabVault!")
            st.rerun()

    route()
