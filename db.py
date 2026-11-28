"""
db.py — cached reads for the Streamlit views (ADR 0006).

The only module besides the views and app.py that imports Streamlit. It wraps
the Streamlit-free repo/ queries in st.cache_data and owns cache
invalidation. Writes never happen here: views call services.py, which writes
through repo/ and then calls the clear_* functions below.

Caches are process-wide (shared by all sessions), so every write must clear
the caches it affects.
"""

import streamlit as st

from repo import (audit, investigations, protocols, results, samples, signatures,
                  specifications, users)


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_all_users():
    """Usernames and roles only — no password hashes leave the database."""
    return users.all_users()


@st.cache_data(ttl=300)
def get_lab_techs():
    """Lab tech usernames, for assignment dropdowns."""
    return users.lab_techs()


# ─────────────────────────────────────────────
# AUDIT TRAIL
# ─────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_audit_trail(limit: int = 200, exclude_actions: tuple = ()):
    """Most recent audit entries, newest first. Short TTL: should feel live."""
    return audit.recent_audit(limit, exclude_actions)


@st.cache_data(ttl=30)
def get_audit_page(user: str = "", action: str = "", limit: int = 100, offset: int = 0):
    """(rows, total) for one filtered page of the full audit trail."""
    return audit.search_audit(user, action, limit, offset)


@st.cache_data(ttl=30)
def get_audit_actions():
    return audit.audit_actions()


# ─────────────────────────────────────────────
# SAMPLES
# ─────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_all_samples(status_filter=None):
    return samples.all_samples(status_filter)


@st.cache_data(ttl=30)
def get_recent_samples(limit: int = 8):
    return samples.recent_samples(limit)


@st.cache_data(ttl=30)
def count_samples_by_status():
    return samples.count_samples_by_status()


@st.cache_data(ttl=30)
def count_samples_by_priority():
    return samples.count_samples_by_priority()


@st.cache_data(ttl=60)
def count_simulated():
    """How much demo data the instance holds — drives the demo-data notice."""
    return samples.count_simulated()


@st.cache_data(ttl=60)
def sample_exists():
    return samples.sample_exists()


# ─────────────────────────────────────────────
# TEST RESULTS
# ─────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_results_for_sample(sample_id: str):
    return results.results_for_sample(sample_id)


@st.cache_data(ttl=30)
def get_all_results():
    return results.all_results()


@st.cache_data(ttl=30)
def get_results_awaiting_review():
    return signatures.awaiting_review()


@st.cache_data(ttl=30)
def get_all_investigations():
    return investigations.all_investigations()


@st.cache_data(ttl=30)
def get_oos_results(limit: int = 10):
    return results.oos_results(limit)


@st.cache_data(ttl=30)
def count_oos_results():
    return results.count_oos_results()


# ─────────────────────────────────────────────
# PROTOCOLS
# ─────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_all_protocols():
    """Long TTL — protocols rarely change; create_protocol clears it."""
    return protocols.all_protocols()


# ─────────────────────────────────────────────
# SPECIFICATIONS
# ─────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_all_specifications():
    """Long TTL — specs change rarely; save_specification clears it."""
    return specifications.all_specs()


# ─────────────────────────────────────────────
# INVALIDATION — called by services.py after a successful commit
# ─────────────────────────────────────────────

def clear_data_caches():
    """Samples, results and the audit trail — every data write affects these."""
    for cached in (get_all_samples, get_recent_samples, count_samples_by_status,
                   count_samples_by_priority, count_simulated, sample_exists,
                   get_results_for_sample, get_all_results, get_oos_results,
                   get_results_awaiting_review, get_all_investigations,
                   count_oos_results):
        cached.clear()
    clear_audit_cache()


def clear_audit_cache():
    """After writing only audit rows (sign-in events, exports)."""
    for cached in (get_audit_trail, get_audit_page, get_audit_actions):
        cached.clear()


def clear_user_caches():
    get_all_users.clear()
    get_lab_techs.clear()


def clear_protocol_cache():
    get_all_protocols.clear()


def clear_spec_cache():
    get_all_specifications.clear()
