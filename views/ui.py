"""Shared helpers for rendering views."""

import html

import streamlit as st

from domain import OOS_CATEGORIES, OOS_INVALIDATED
from logs import log_exception


def esc(value) -> str:
    """
    Escape a value for interpolation into st.markdown(..., unsafe_allow_html=True).
    Every database or user-supplied value in a raw-HTML block must go through
    this, otherwise stored text is rendered as markup for every viewer.
    """
    return html.escape("" if value is None else str(value))


SIMULATED_LABEL = "SIMULATED"


def simulated_text(flag) -> str:
    """'Yes'/'No' for table columns; missing flags count as real data."""
    return "Yes" if flag else "No"

def oos_summary(breakdown) -> str:
    """One line on where OOS results stand, from db.get_oos_breakdown() (ADR 0019)."""
    counted = ", ".join(f"{breakdown[c]} {c.lower()}" for c in OOS_CATEGORIES
                        if c != OOS_INVALIDATED)
    return (f"Counted: {counted}. Not counted: {breakdown[OOS_INVALIDATED]} invalidated "
            "by a laboratory error.")


def show_error(message: str, **context) -> str:
    """
    For an unexpected exception, inside an `except` block: show `message`
    (plain words, no exception text) with a reference, and log the traceback
    under that reference (audit M8, ADR 0021). Returns the reference.
    """
    ref = log_exception(message, **context)
    st.error(f"{message} Please try again. If it keeps happening, give an administrator "
             f"this reference: **{ref}**.")
    return ref


def how_to_add_samples() -> str:
    """Where samples come from on this instance: the FDA demo import exists only
    on demo instances (ADR 0026); everywhere else, Sample Intake."""
    from config import demo_mode
    if demo_mode():
        return "Click **🔄 Import FDA Data** in the sidebar, or register one in **Sample Intake**."
    return "Register the first one in **Sample Intake**."


# Shown for a sample with no assignee (assigned_to is NULL).
UNASSIGNED = "Unassigned"


def page_header(title: str, subtitle: str) -> None:
    """
    The dark banner at the top of every page (styled by .lv-header in app.py).
    A leading emoji is decorative: it's hidden from screen readers, which
    would otherwise read its name before the title (audit U5).
    """
    icon, _, text = title.partition(" ")
    if icon.isascii() or not text:
        icon, text = "", title
    icon_html = f'<span aria-hidden="true">{esc(icon)}</span> ' if icon else ""
    st.markdown(f"""
        <div class="lv-header">
            <div><h1>{icon_html}{esc(text)}</h1>
            <span class="lv-subtitle">{esc(subtitle)}</span></div>
        </div>
    """, unsafe_allow_html=True)
