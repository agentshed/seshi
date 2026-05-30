"""Tests for external .tcss stylesheet refactor (Item 15)."""
from pathlib import Path

from seshi.themes import THEMES, get_theme
from seshi.tui.styles import theme_css


def test_tcss_file_exists():
    tcss = Path(__file__).parent.parent / "src" / "seshi" / "tui" / "seshi.tcss"
    assert tcss.exists(), f"seshi.tcss not found at {tcss}"


def test_tcss_file_has_structural_rules():
    tcss = Path(__file__).parent.parent / "src" / "seshi" / "tui" / "seshi.tcss"
    content = tcss.read_text()
    assert "#header" in content
    assert "#footer" in content
    assert "#preview" in content
    assert "#session-list" in content
    assert "#sessions-pane" in content
    assert "height:" in content
    assert "width:" in content
    assert "dock:" in content


def test_tcss_no_color_values():
    tcss = Path(__file__).parent.parent / "src" / "seshi" / "tui" / "seshi.tcss"
    content = tcss.read_text()
    assert "color:" not in content
    assert "background:" not in content
    assert "border:" not in content


def test_theme_css_has_only_color_rules():
    coral = get_theme("coral")
    css = theme_css(coral)
    assert "color:" in css or "background:" in css
    assert "height: 5" not in css
    assert "width: 45" not in css
    assert "dock: bottom" not in css
    assert "min-height:" not in css


def test_all_themes_generate_css():
    for name in THEMES:
        palette = get_theme(name)
        css = theme_css(palette)
        assert css, f"Theme {name} generated empty CSS"
        assert "Screen {" in css


def test_app_has_css_path():
    from seshi.tui.app import SeshiApp
    assert hasattr(SeshiApp, "CSS_PATH")
    assert SeshiApp.CSS_PATH == "seshi.tcss"
