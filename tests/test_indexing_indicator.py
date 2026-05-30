"""Tests for loading indicator during background indexing (Phase B, Item 7)."""
from seshi.tui.header import Header


def test_header_shows_indexing_when_flag_true():
    header = Header()
    header.indexing = True
    rendered = header.render().plain
    assert "indexing" in rendered


def test_header_hides_indexing_when_flag_false():
    header = Header()
    header.indexing = False
    rendered = header.render().plain
    assert "indexing" not in rendered


def test_header_indexing_defaults_to_false():
    header = Header()
    assert header.indexing is False
    rendered = header.render().plain
    assert "indexing" not in rendered


def test_header_indexing_with_session_counts():
    header = Header()
    header.session_count = 45
    header.shown_count = 12
    header.indexing = True
    rendered = header.render().plain
    assert "12 of 45 sessions" in rendered
    assert "indexing" in rendered


def test_header_indexing_position_after_version():
    header = Header()
    header.indexing = True
    rendered = header.render().plain
    version_pos = rendered.find("v0.1.0")
    indexing_pos = rendered.find("indexing")
    assert version_pos < indexing_pos, "indexing indicator should appear after version"


def test_header_render_stable_without_indexing():
    header = Header()
    header.session_count = 10
    header.shown_count = 10
    rendered = header.render().plain
    assert "█▀▀ █▀▀ █▀▀" in rendered
    assert "Seshi" in rendered
    assert "10 of 10 sessions" in rendered
    assert "indexing" not in rendered
