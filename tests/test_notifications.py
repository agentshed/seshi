"""Tests for flash notification on completed actions."""
import time
from unittest.mock import MagicMock

from seshi.tui.sessions import SessionsList


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


def _make_widget_with_mock_app(tmp_db, session_id="s1", **kwargs):
    _insert_session(tmp_db, session_id, **kwargs)
    sl = SessionsList(tmp_db)
    mock_app = MagicMock()
    mock_app._quit_toast_active = False
    original_app = type(sl).app
    type(sl).app = property(lambda self: mock_app)
    return sl, mock_app, original_app


def test_rename_triggers_notification(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db, custom_name="old-name")
    try:
        sl._input_buffer = "new-name"
        sl._apply_rename()
        mock_app.notify.assert_called()
        msg = mock_app.notify.call_args[0][0]
        assert "new-name" in msg
    finally:
        type(sl).app = orig


def test_tag_triggers_notification(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db)
    try:
        sl._input_buffer = "prod"
        sl._apply_tag()
        mock_app.notify.assert_called_once()
        msg = mock_app.notify.call_args[0][0]
        assert "prod" in msg
    finally:
        type(sl).app = orig


def test_favorite_triggers_notification(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db)
    try:
        sl._toggle_favorite()
        mock_app.notify.assert_called_once()
        msg = mock_app.notify.call_args[0][0]
        assert "favorite" in msg.lower()
    finally:
        type(sl).app = orig


def test_archive_triggers_notification(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db)
    try:
        sl._execute_archive([sl.sessions[0].session_id])
        mock_app.notify.assert_called_once()
        msg = mock_app.notify.call_args[0][0]
        assert "rchived" in msg  # "Archived"
    finally:
        type(sl).app = orig


def test_delete_triggers_notification(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db)
    try:
        sid = sl.sessions[0].session_id
        sl._execute_delete([sid])
        mock_app.notify.assert_called_once()
        msg = mock_app.notify.call_args[0][0]
        assert "eleted" in msg  # "Deleted"
        assert mock_app.notify.call_args[1].get("severity") == "warning"
    finally:
        type(sl).app = orig


def test_bulk_delete_notification_shows_count(tmp_db):
    for i in range(3):
        _insert_session(tmp_db, f"s{i}")
    sl = SessionsList(tmp_db)
    mock_app = MagicMock()
    mock_app._quit_toast_active = False
    original_app = type(sl).app
    type(sl).app = property(lambda self: mock_app)
    try:
        sids = [s.session_id for s in sl.sessions[:3]]
        sl._execute_delete(sids)
        msg = mock_app.notify.call_args[0][0]
        assert "3 sessions" in msg
    finally:
        type(sl).app = original_app


def test_notification_not_called_on_cancelled_rename(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db, custom_name="original")
    try:
        sl._input_mode = "rename"
        sl._input_buffer = "new-name"
        # Cancel — just clear the mode without applying
        sl._input_mode = ""
        sl._input_buffer = ""
        mock_app.notify.assert_not_called()
    finally:
        type(sl).app = orig


def test_notification_not_called_on_cancelled_tag(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db)
    try:
        sl._input_mode = "tag"
        sl._input_buffer = "sometag"
        # Cancel without applying
        sl._input_mode = ""
        sl._input_buffer = ""
        mock_app.notify.assert_not_called()
    finally:
        type(sl).app = orig


def test_notification_not_called_on_invalid_tag(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db)
    try:
        sl._input_buffer = "invalid tag with spaces"
        sl._apply_tag()
        mock_app.notify.assert_not_called()
    finally:
        type(sl).app = orig
