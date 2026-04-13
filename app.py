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

st.set_page_config(
    page_title="LabVault",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# GLOBAL STYLES
# ─────────────────────────────────────────────

st.markdown("""
<style>
    /* Sidebar */
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

    /* Top header bar */
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
        opacity: 0.75;
    }

    /* Metric cards */
    .metric-card {
        background: white;
        border-radius: 10px;
        padding: 20px;
        border-left: 5px solid #1a4a8a;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    .metric-card.critical { border-left-color: #d32f2f; }
    .metric-card.warning  { border-left-color: #f57c00; }
    .metric-card.success  { border-left-color: #2e7d32; }

    /* Status badges */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    .badge-pending    { background:#fff3e0; color:#e65100; }
    .badge-progress   { background:#e3f2fd; color:#1565c0; }
    .badge-completed  { background:#e8f5e9; color:#2e7d32; }
    .badge-rejected   { background:#fce4ec; color:#c62828; }
    .badge-pass       { background:#e8f5e9; color:#2e7d32; }
    .badge-fail       { background:#fce4ec; color:#c62828; }
    .badge-critical   { background:#fce4ec; color:#c62828; }
    .badge-major      { background:#fff3e0; color:#e65100; }
    .badge-minor      { background:#e8f5e9; color:#2e7d32; }

    /* Login box */
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

    /* Hide Streamlit default elements */
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    header    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# FIRST-RUN SETUP
# ─────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def setup():
    """Initialize DB and seed data exactly once per session."""
    init_db()
    seed_users()
    seed_protocols()
    return True

setup()


# ─────────────────────────────────────────────
# SESSION STATE DEFAULTS
# ─────────────────────────────────────────────

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"
if "fda_seeded" not in st.session_state:
    st.session_state.fda_seeded = False


# ─────────────────────────────────────────────
# LOGIN SCREEN
# ─────────────────────────────────────────────

def show_login():
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

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("#### Sign in to your account")
        username = st.text_input("Username", placeholder="e.g. admin")
        password = st.text_input("Password", type="password", placeholder="••••••••")

        if st.button("Sign In", use_container_width=True, type="primary"):
            user = authenticate(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid username or password.")

        st.markdown("---")
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
        st.markdown(f"**{user['username']}** · *{role.replace('_', ' ').title()}*")
        st.markdown("---")

        pages = [
            "📊  Dashboard",
            "🧫  Sample Intake",
            "🔬  Sample Tracking",
            "📋  Test Results",
            "📄  Protocols",
            "📈  Reports",
            "🕵️  Audit Trail",
        ]

        # Admin-only: show user management hint
        if role == "admin":
            pages.append("⚙️  Admin")

        choice = st.radio("Navigation", pages, label_visibility="collapsed")

        # Strip emoji prefix to get clean page name
        clean = choice.split("  ", 1)[-1].strip()
        st.session_state.page = clean

        st.markdown("---")

        # FDA seed button — admin only
        if role == "admin":
            st.markdown("**Data Management**")
            if not sample_exists():
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

        if st.button("Sign Out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()


# ─────────────────────────────────────────────
# PAGE ROUTER
# ─────────────────────────────────────────────

def route():
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
    show_login()
else:
    show_sidebar()

    # Auto-import FDA data on first login if DB is empty
    if not sample_exists() and not st.session_state.fda_seeded:
        with st.spinner("🔬 First launch — importing real FDA pharmaceutical data..."):
            result = seed_from_fda(limit=100)
        if result["success"]:
            st.session_state.fda_seeded = True
            st.success(f"✅ {result['count']} real FDA recall records imported. Welcome to LabVault!")
            st.rerun()

    route()
