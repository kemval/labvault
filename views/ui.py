"""Shared helpers for rendering views."""

import html


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
