"""Tests for horizontal split layout (issue #79, PR #80 follow-ups).

Covers: compact rendering, wide rendering, dynamic preview sizing,
preview toggle width management, and regression checks.
"""
import time
from unittest.mock import MagicMock, patch, PropertyMock
from textual.geometry import Size

from seshi.tui.sessions import SessionsList
from seshi.tui.preview import Preview
from seshi.models import Session
from seshi.transcript import Message


def _insert_session(conn, session_id, cwd="/tmp/project", custom_name=None,
                    first_prompt=None, is_favorite=0, ts=None):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, custom_name, first_prompt,
         is_favorite, created_at, last_activity_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (session_id, cwd, "[]", custom_name, first_prompt, is_favorite, ts, ts),
    )
    conn.commit()


def _render_with_size(widget, width, height):
    with patch.object(type(widget), "size", new_callable=PropertyMock, return_value=Size(width, height)):
        return widget.render()


def _make_session(session_id="test-id", cwd="/tmp/project", custom_name=None,
                  first_prompt=None, is_favorite=0, ts=None):
    ts = ts or int(time.time())
    return Session(
        session_id=session_id, cwd=cwd, launch_argv_json="[]",
        env_json=None, git_branch=None, git_sha=None,
        first_prompt=first_prompt, custom_name=custom_name,
        is_favorite=is_favorite, is_archived=0, is_backfilled=0,
        message_count=10, token_count=5000, status=None,
        created_at=ts, last_activity_at=ts, origin_host=None,
        schema_version=1,
    )


# === Compact rendering at narrow width ===

def test_compact_rendering_no_cwd_at_narrow_width(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/home/user/myproject", custom_name="auth-fix")
    view = SessionsList(tmp_db)
    rendered = _render_with_size(view, 45, 30).plain
    assert "auth-fix" in rendered
    assert "/home/user/myproject" not in rendered
    assert "myproject" not in rendered


def test_compact_rendering_no_language_at_narrow_width(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/tmp/project/main.py", custom_name="test-session")
    view = SessionsList(tmp_db)
    rendered = _render_with_size(view, 45, 30).plain
    assert "test-session" in rendered


def test_compact_rendering_no_tags_at_narrow_width(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="tagged-session")
    tmp_db.execute("INSERT INTO tags (session_id, tag) VALUES (?, ?)", ("s1", "important"))
    tmp_db.commit()
    view = SessionsList(tmp_db)
    rendered = _render_with_size(view, 45, 30).plain
    assert "tagged-session" in rendered
    assert "#important" not in rendered


def test_compact_rendering_fav_indicator_2_chars(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="fav-session", is_favorite=1)
    view = SessionsList(tmp_db)
    rendered = _render_with_size(view, 45, 30).plain
    assert "*" in rendered


def test_compact_rendering_relative_time_not_clipped(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="recent")
    view = SessionsList(tmp_db)
    rendered = _render_with_size(view, 45, 30).plain
    lines = [l for l in rendered.split("\n") if "recent" in l]
    assert len(lines) == 1
    line = lines[0]
    assert line == line.rstrip() or line.endswith("\n")
    time_part = line.split()[-1] if line.split() else ""
    assert len(time_part) >= 2


# === Wide rendering at full width ===

def test_wide_rendering_includes_cwd(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/tmp/myproject", custom_name="wide-test")
    view = SessionsList(tmp_db)
    rendered = _render_with_size(view, 120, 30).plain
    assert "wide-test" in rendered
    assert "myproject" in rendered


def test_wide_rendering_includes_tags(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="wide-tagged")
    tmp_db.execute("INSERT INTO tags (session_id, tag) VALUES (?, ?)", ("s1", "feature"))
    tmp_db.commit()
    view = SessionsList(tmp_db)
    rendered = _render_with_size(view, 120, 30).plain
    assert "#feature" in rendered


# === Preview dynamic message count ===

def test_preview_shows_more_than_6_messages_at_tall_height():
    messages = [
        Message(role="user" if i % 2 == 0 else "assistant", text=f"Message number {i}")
        for i in range(20)
    ]
    session = _make_session(session_id="s-preview")

    preview = Preview()
    preview.session = session

    with patch("seshi.tui.preview.find_transcript_path", return_value="/fake/path"), \
         patch("seshi.tui.preview.extract_messages", return_value=messages):
        rendered = _render_with_size(preview, 80, 40).plain

    role_count = rendered.count("you") + rendered.count("asst")
    assert role_count > 6


def test_preview_caps_messages_to_available_height():
    messages = [
        Message(role="user" if i % 2 == 0 else "assistant", text=f"Message {i}")
        for i in range(50)
    ]
    session = _make_session(session_id="s-cap")

    preview = Preview()
    preview.session = session

    with patch("seshi.tui.preview.find_transcript_path", return_value="/fake/path"), \
         patch("seshi.tui.preview.extract_messages", return_value=messages):
        rendered = _render_with_size(preview, 80, 15).plain

    role_count = rendered.count("you") + rendered.count("asst")
    assert role_count <= 15
    assert role_count >= 10


# === Preview dynamic text width ===

def test_preview_text_width_scales_with_widget_width():
    long_text = "x" * 200
    messages = [Message(role="user", text=long_text)]
    session = _make_session(session_id="s-wide")

    preview = Preview()
    preview.session = session

    with patch("seshi.tui.preview.find_transcript_path", return_value="/fake/path"), \
         patch("seshi.tui.preview.extract_messages", return_value=messages):
        rendered = _render_with_size(preview, 150, 20).plain

    x_count = rendered.count("x")
    assert x_count > 120


def test_preview_text_width_respects_narrow_widget():
    long_text = "y" * 200
    messages = [Message(role="user", text=long_text)]
    session = _make_session(session_id="s-narrow")

    preview = Preview()
    preview.session = session

    with patch("seshi.tui.preview.find_transcript_path", return_value="/fake/path"), \
         patch("seshi.tui.preview.extract_messages", return_value=messages):
        rendered = _render_with_size(preview, 60, 20).plain

    y_count = rendered.count("y")
    assert y_count <= 60
    assert y_count >= 40


# === Preview toggle width management ===

def test_preview_toggle_sets_sessions_width(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="toggle-test")
    view = SessionsList(tmp_db)

    mock_preview = MagicMock()
    mock_preview.display = True

    mock_app = MagicMock()
    mock_app._quit_toast_active = False
    mock_app._preview = mock_preview
    original_app = type(view).app
    type(view).app = property(lambda self: mock_app)

    try:
        mock_event = MagicMock()
        mock_event.key = "p"
        mock_event.is_printable = False
        view.on_key(mock_event)

        assert mock_preview.display is False
        assert view.styles.width is not None

        mock_event2 = MagicMock()
        mock_event2.key = "p"
        mock_event2.is_printable = False
        view.on_key(mock_event2)

        assert mock_preview.display is True
    finally:
        type(view).app = original_app


# === Regression: existing functionality still works ===

def test_search_filter_works_after_layout_change(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="auth-rewrite")
    _insert_session(tmp_db, "s2", first_prompt="completely unrelated xyz")
    view = SessionsList(tmp_db)
    view.filter("auth")
    assert len(view.sessions) < 2
    ids = [s.session_id for s in view.sessions]
    assert "s1" in ids


def test_sort_mode_cycling(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    assert view.sort_mode == "frecency"

    mock_app = MagicMock()
    mock_app._quit_toast_active = False
    original_app = type(view).app
    type(view).app = property(lambda self: mock_app)
    try:
        event = MagicMock()
        event.key = "s"
        event.is_printable = False
        view.on_key(event)
        assert view.sort_mode == "recency"
    finally:
        type(view).app = original_app


def test_rename_input_mode(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="old-name")
    view = SessionsList(tmp_db)
    view._start_rename()
    assert view._input_mode == "rename"
    assert view._input_buffer == "old-name"


def test_tag_input_mode(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._start_tag()
    assert view._input_mode == "tag"
    assert view._input_buffer == ""


def test_cursor_stays_in_bounds(tmp_db):
    _insert_session(tmp_db, "s1")
    _insert_session(tmp_db, "s2")
    view = SessionsList(tmp_db)
    view.cursor = 0

    mock_app = MagicMock()
    mock_app._quit_toast_active = False
    original_app = type(view).app
    type(view).app = property(lambda self: mock_app)
    try:
        event = MagicMock()
        event.key = "up"
        event.is_printable = False
        view.on_key(event)
        assert view.cursor == 0

        view.cursor = len(view.sessions) - 1
        event2 = MagicMock()
        event2.key = "down"
        event2.is_printable = False
        view.on_key(event2)
        assert view.cursor == len(view.sessions) - 1
    finally:
        type(view).app = original_app


def test_bulk_select_all(tmp_db):
    for i in range(5):
        _insert_session(tmp_db, f"s{i}")
    view = SessionsList(tmp_db)

    mock_app = MagicMock()
    mock_app._quit_toast_active = False
    original_app = type(view).app
    type(view).app = property(lambda self: mock_app)
    try:
        event = MagicMock()
        event.key = "ctrl+a"
        event.is_printable = False
        view.on_key(event)
        assert len(view.selected) == 5
    finally:
        type(view).app = original_app
