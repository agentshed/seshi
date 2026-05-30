"""Tests for NO_COLOR support and theme backgrounds (Item 14)."""
import os
from unittest import mock

from seshi.themes import Palette, THEMES, get_theme
from seshi.tui.styles import theme_css


def test_palette_has_bg_field():
    from dataclasses import fields
    field_names = {f.name for f in fields(Palette)}
    assert "bg" in field_names
    coral = get_theme("coral")
    assert coral.bg is not None
    assert coral.bg.startswith("#")


def test_all_themes_have_bg_field():
    for name, palette in THEMES.items():
        assert palette.bg, f"Theme {name} missing bg field"
        assert palette.bg.startswith("#"), f"Theme {name} bg not a color: {palette.bg}"


def test_no_explicit_black_background_in_css():
    for name, palette in THEMES.items():
        css = theme_css(palette)
        assert "#000000" not in css, f"Theme {name} still uses hardcoded #000000"


def test_css_uses_palette_bg():
    coral = get_theme("coral")
    css = theme_css(coral)
    assert coral.bg in css


def test_all_themes_generate_valid_css():
    for name in THEMES:
        palette = get_theme(name)
        css = theme_css(palette)
        assert css
        assert "Screen {" in css
        assert "#header" in css
        assert "#footer" in css


def test_no_color_env_forces_mono_theme():
    with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
        from seshi.tui.app import SeshiApp
        app = SeshiApp()
        assert app._no_color is True
        assert app._palette == get_theme("mono")


def test_no_color_env_absent_uses_default():
    env = os.environ.copy()
    env.pop("NO_COLOR", None)
    with mock.patch.dict(os.environ, env, clear=True):
        from seshi.tui.app import SeshiApp
        app = SeshiApp()
        assert app._no_color is False


def test_preview_has_color_reactives():
    from seshi.tui.preview import Preview
    p = Preview()
    assert hasattr(p, "user_color")
    assert hasattr(p, "assistant_color")
    assert p.user_color.startswith("#")
    assert p.assistant_color.startswith("#")


def test_preview_color_defaults():
    from seshi.tui.preview import Preview
    p = Preview()
    p.user_color = "#FF0000"
    assert p.user_color == "#FF0000"
    p.assistant_color = "#00FF00"
    assert p.assistant_color == "#00FF00"
