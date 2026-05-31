"""Tests for footer overflow handling at narrow terminal widths."""
from collections import namedtuple
from unittest.mock import PropertyMock

from seshi.tui.footer import Footer

_Size = namedtuple("Size", ["width", "height"])
_original_size = Footer.size


def _render_footer_at_width(width, view="sessions", mode="normal"):
    footer = Footer()
    footer.view = view
    footer.mode = mode
    type(footer).size = PropertyMock(return_value=_Size(width, 1))
    try:
        return footer.render()
    finally:
        type(footer).size = _original_size


def test_footer_renders_all_keys_at_wide_width():
    rendered = _render_footer_at_width(200)
    text = rendered.plain
    for keyword in ["resume", "search", "fav", "delete", "sort", "rename",
                    "tag", "archive", "expand", "hide", "preview", "select", "help"]:
        assert keyword in text, f"Expected '{keyword}' in footer at wide width: {text}"
    assert "more" not in text


def test_footer_truncates_at_narrow_width():
    rendered = _render_footer_at_width(50)
    text = rendered.plain
    assert "resume" in text
    assert "search" in text
    assert "more" in text
    # Low priority items should be cut
    assert "preview" not in text


def test_footer_truncates_at_medium_width():
    rendered = _render_footer_at_width(80)
    text = rendered.plain
    assert "resume" in text
    assert "search" in text
    # At 80 chars, some keys should be present but not all
    has_more = "more" in text
    has_all = all(k in text for k in ["preview", "select", "help"])
    # Either everything fits or "more" is shown
    assert has_more or has_all


def test_footer_minimum_width_edge_case():
    rendered = _render_footer_at_width(15)
    text = rendered.plain
    # Should not crash, should show something
    assert len(text) > 0


def test_footer_rename_mode_not_truncated():
    rendered = _render_footer_at_width(40, mode="rename")
    text = rendered.plain
    assert "save" in text
    assert "cancel" in text


def test_footer_tag_mode_not_truncated():
    rendered = _render_footer_at_width(40, mode="tag")
    text = rendered.plain
    assert "apply" in text
    assert "cancel" in text


def test_footer_projects_view_keys_fit():
    rendered = _render_footer_at_width(60, view="projects")
    text = rendered.plain
    assert "open" in text
    assert "favorite" in text


def test_footer_overview_view_always_fits():
    rendered = _render_footer_at_width(40, view="overview")
    text = rendered.plain
    assert "scroll" in text
    assert "more" not in text


def test_footer_help_view_always_fits():
    rendered = _render_footer_at_width(40, view="help")
    text = rendered.plain
    assert "scroll" in text
    assert "more" not in text
