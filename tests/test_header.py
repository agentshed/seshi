"""Tests for the compact single-line header."""
from seshi.tui.header import Header


def test_compact_header_renders_single_line():
    header = Header()
    header.shown_count = 12
    header.session_count = 45
    rendered = header.render()
    text = rendered.plain
    assert "\n" not in text
    assert "SESHI" in text


def test_compact_header_shows_version():
    header = Header()
    rendered = header.render()
    assert "v" in rendered.plain


def test_compact_header_shows_counts():
    header = Header()
    header.shown_count = 12
    header.session_count = 45
    text = header.render().plain
    assert "12" in text
    assert "45" in text
    assert "sessions" in text


def test_compact_header_accent_applied():
    header = Header()
    header.accent = "#FF0000"
    rendered = header.render()
    spans = rendered._spans
    has_accent = any("#FF0000" in str(s.style) or "ff0000" in str(s.style).lower() for s in spans)
    assert has_accent, f"Expected accent color in spans: {spans}"


def test_compact_header_zero_sessions():
    header = Header()
    header.shown_count = 0
    header.session_count = 0
    text = header.render().plain
    assert "0" in text
    assert "sessions" in text


def test_compact_header_large_counts():
    header = Header()
    header.shown_count = 9999
    header.session_count = 99999
    text = header.render().plain
    assert "9999" in text
    assert "99999" in text


def test_compact_header_sort_mode():
    header = Header()
    header.sort_mode = "frecency"
    text = header.render().plain
    assert "frecency" in text


def test_compact_header_indexing_indicator():
    header = Header()
    header.indexing = True
    text = header.render().plain
    assert "indexing" in text


def test_compact_header_no_indexing_when_false():
    header = Header()
    header.indexing = False
    text = header.render().plain
    assert "indexing" not in text


def test_compact_header_no_ascii_art():
    header = Header()
    text = header.render().plain
    assert "█▀▀" not in text
    assert "▀▀█" not in text
    assert "▀▀▀" not in text
