from seshi.themes import THEMES, get_theme, DEFAULT_THEME, Palette
import re

PALETTE_FIELDS = [
    "accent", "accent_soft", "accent_deep", "fg", "fg_muted", "fg_dim",
    "bg_selected", "fg_selected", "border", "border_dim", "user", "assistant",
]

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_all_themes_have_all_fields():
    for name, palette in THEMES.items():
        for field in PALETTE_FIELDS:
            assert hasattr(palette, field), f"{name} missing {field}"


def test_all_colors_are_valid_hex():
    for name, palette in THEMES.items():
        for field in PALETTE_FIELDS:
            val = getattr(palette, field)
            assert HEX_RE.match(val), f"{name}.{field} = {val!r} is not valid hex"


def test_fifteen_themes():
    assert len(THEMES) == 15
    expected = {
        "coral", "catppuccin", "gruvbox", "nord", "mono",
        "dracula", "solarized", "tokyo-night", "rose-pine", "kanagawa",
        "one-dark", "monokai", "everforest", "ayu", "cyberdream",
    }
    assert set(THEMES.keys()) == expected


def test_get_theme_valid():
    p = get_theme("nord")
    assert isinstance(p, Palette)
    assert p.accent == "#88c0d0"  # nord accent unchanged


def test_get_theme_unknown_falls_back():
    p = get_theme("nonexistent")
    assert p == THEMES[DEFAULT_THEME]
