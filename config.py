"""
config.py — deployment settings for LabVault.

Settings are read from environment variables first, then from Streamlit
secrets (.streamlit/secrets.toml locally, or the Secrets panel on Streamlit
Community Cloud). See docs/adr/0001-deployment-modes.md.

    LABVAULT_DEMO_MODE       "true" → seed public demo accounts and show their
                             credentials. Anything else (or unset) → secure mode.
    LABVAULT_ADMIN_PASSWORD  Secure mode only: password for the initial `admin`
                             account, used once when the users table is empty.
    LABVAULT_DB_PATH         Environment only: where the SQLite database lives
                             (default ./labvault.db).
                             In production: a file on a persistent volume (ADR 0023).
    LITESTREAM_REPLICA_URL   Environment only. Set when Litestream streams the database to object
                             storage (deploy/start.sh). Shown on the Admin page.
"""

import os


class ConfigError(RuntimeError):
    """The deployment is misconfigured; the app must not start."""


def _setting(name: str):
    value = os.environ.get(name)
    if value is not None:
        return value
    try:
        # Imported here so config (and repo/, which raises ConfigError) can be
        # used without Streamlit installed or running.
        import streamlit as st
        value = st.secrets.get(name)
    except Exception:
        # No secrets file configured — st.secrets raises rather than returning None.
        return None
    return None if value is None else str(value)


def demo_mode() -> bool:
    # Secure by default: only an explicit opt-in enables the demo accounts.
    return (_setting("LABVAULT_DEMO_MODE") or "").strip().lower() in {"1", "true", "yes"}


def admin_password():
    value = _setting("LABVAULT_ADMIN_PASSWORD")
    return value if value else None


DEFAULT_DB_PATH = "labvault.db"


def db_path() -> str:
    """
    The SQLite database file (ADR 0023). Read from the environment only: it is
    set by the host, and repo/ must not import Streamlit to read secrets.
    """
    value = (os.environ.get("LABVAULT_DB_PATH") or "").strip()
    return value or DEFAULT_DB_PATH


def backup_replica():
    """Where Litestream replicates the database, or None if it doesn't (ADR 0023).
    Only the scheme and location are returned, never credentials."""
    from urllib.parse import urlsplit
    value = (os.environ.get("LITESTREAM_REPLICA_URL") or "").strip()
    if not value:
        return None
    url = urlsplit(value)
    return f"{url.scheme}://{url.hostname or ''}{url.path}" if url.scheme else None
