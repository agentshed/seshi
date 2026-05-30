"""Tests for footer overflow handling at narrow terminal widths."""
from unittest.mock import MagicMock, PropertyMock

from seshi.tui.footer import Footer


def _render_footer_at_width(width, view="sessions", mode="normal"):
    footer = Footer()
    footer.view = view
    footer.mode = mode
    mock_size = MagicMock()
    mock_size.width = width
    mock_size.height = 1
    type(footer).size = PropertyMock(return_value=mock_size)
    return footer.render()


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
