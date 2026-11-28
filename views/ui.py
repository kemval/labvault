"""Shared helpers for rendering views."""

import html

import streamlit as st


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
