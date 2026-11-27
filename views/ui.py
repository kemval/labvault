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
    """The dark banner at the top of every page (styled by .lv-header in app.py)."""
    st.markdown(f"""
        <div class="lv-header">
            <div><h1>{esc(title)}</h1>
            <span>{esc(subtitle)}</span></div>
        </div>
    """, unsafe_allow_html=True)
