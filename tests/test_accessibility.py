"""Accessibility checks: contrast, keyboard sign-in, screen-reader labels (audit U1/U5, ADR 0018)."""
import glob
import os
import re
import tomllib

import pytest

from test_app_login import login, no_network, page_text, run_app  # noqa: F401
from views.navigation import PAGES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AA = 4.5      # WCAG 2.2 AA, normal-size text


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _luminance(hex_color):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg, bg, alpha):
    return "#" + "".join(f"{round(alpha * f + (1 - alpha) * b):02x}"
                         for f, b in zip(_rgb(fg), _rgb(bg)))


def test_contrast_formula_matches_known_values():
    assert contrast("#000", "#fff") == pytest.approx(21)
    assert contrast("#767676", "#fff") == pytest.approx(4.54, abs=0.01)


HEX = r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b"
TEXT_COLOR = re.compile(rf"(?<![-\w])color:\s*({HEX})")
BACKGROUND = re.compile(rf"background(?:-color)?:\s*({HEX})")


def color_pairs():
    """
    Every hard-coded text colour in the app with the background it sits on:
    one declared in the same CSS rule or inline style, else the white page or
    card. Yields (where, text colour, background).
    """
    for path in [os.path.join(ROOT, "app.py"), *glob.glob(os.path.join(ROOT, "views", "*.py"))]:
        source = open(path, encoding="utf-8").read()
        for m in TEXT_COLOR.finditer(source):
            start = max(source.rfind(c, 0, m.start()) for c in '{"')
            ends = [i for i in (source.find(c, m.end()) for c in '}"') if i != -1]
            group = source[start:min(ends)]
            bg = BACKGROUND.search(group)
            line = source.count("\n", 0, m.start()) + 1
            yield f"{os.path.basename(path)}:{line}", m.group(1), bg.group(1) if bg else "#ffffff"


def test_scanner_finds_the_colours():
    assert len(list(color_pairs())) > 20


@pytest.mark.parametrize("where, fg, bg", list(color_pairs()))
def test_text_colours_meet_wcag_aa(where, fg, bg):
    assert contrast(fg, bg) >= AA, f"{where}: {fg} on {bg} is {contrast(fg, bg):.2f}:1"


def test_header_subtitle_meets_aa_on_its_lightest_background():
    # white at 75 % opacity over the gradient's lighter end (#1a4a8a)
    assert contrast(blend("#ffffff", "#1a4a8a", 0.75), "#1a4a8a") >= AA


def test_theme_colours_meet_aa():
    theme = tomllib.load(open(os.path.join(ROOT, ".streamlit", "config.toml"), "rb"))["theme"]
    side = theme["sidebar"]
    assert theme["base"] == "light"
    assert contrast(side["textColor"], side["backgroundColor"]) >= AA
    assert contrast(side["textColor"], side["secondaryBackgroundColor"]) >= AA
    assert contrast("#ffffff", theme["primaryColor"]) >= AA       # primary button text


def test_sidebar_is_not_recoloured_by_a_blanket_css_rule():
    # [data-testid="stSidebar"] * { color: … !important } overrode alerts and focus.
    assert '[data-testid="stSidebar"] *' not in open(os.path.join(ROOT, "app.py")).read()


# ── keyboard and screen readers ─────────────────────────────

def test_sign_in_fields_are_in_a_form_so_enter_submits(lab_db, settings):
    settings(demo="true")
    at = run_app()
    assert [w.form_id for w in at.text_input] == ["login", "login"]
    assert any(b.label == "Sign In" and b.form_id == "login" for b in at.button)
    login(at, "kembly", "lab2024")
    assert at.session_state.logged_in


def test_navigation_titles_are_plain_text_with_hidden_icons():
    for title, _, icon, _ in PAGES:
        assert title.isascii(), title                    # no emoji for screen readers to read
        assert re.fullmatch(r":material/[a-z_]+:", icon), icon


def test_page_header_hides_its_decorative_emoji(lab_db, settings):
    settings(demo="true")
    at = login(run_app(), "kembly", "lab2024")
    assert '<h1><span aria-hidden="true">📊</span> Dashboard</h1>' in page_text(at)
