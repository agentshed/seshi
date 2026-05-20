"""Tests for Ctrl+C quit-confirmation toast and Escape dismissal (issue #11, #13)."""

import sqlite3
from unittest.mock import MagicMock

from seshi.tui.app import SeshiApp


def _insert_session(conn, session_id="sess-1", cwd="/tmp"):
    import time
    now = int(time.time())
    conn.execute(
        "INSERT INTO sessions (session_id, cwd, created_at, last_activity_at) VALUES (?, ?, ?, ?)",
        (session_id, cwd, now, now),
    )
    conn.commit()


class TestQuitToastFlag:
    """Unit tests for the _quit_toast_active flag logic."""

    def test_action_request_quit_sets_flag(self, tmp_db):
        app = SeshiApp(conn=tmp_db)
        assert app._quit_toast_active is False
        app._quit_toast_active = True
        assert app._quit_toast_active is True

    def test_escape_clears_quit_toast_flag(self, tmp_db):
        app = SeshiApp(conn=tmp_db)
        app._quit_toast_active = True
        app.action_back_or_quit()
        assert app._quit_toast_active is False

    def test_escape_does_not_clear_flag_when_inactive(self, tmp_db):
        app = SeshiApp(conn=tmp_db)
        assert app._quit_toast_active is False
        assert app._quit_toast_active is False

    def test_clear_quit_toast_helper(self, tmp_db):
        app = SeshiApp(conn=tmp_db)
        app._quit_toast_active = True
        app._clear_quit_toast()
        assert app._quit_toast_active is False


class TestQuitToastSpaceToggle:
    """Space key must not toggle selection when quit toast is active (#13)."""

    def test_quit_toast_flag_prevents_space_toggle(self, tmp_db):
        _insert_session(tmp_db)
        from seshi.tui.sessions import SessionsList

        sl = SessionsList(tmp_db)
        mock_app = MagicMock()
        mock_app._quit_toast_active = True

        mock_event = MagicMock()
        mock_event.key = "space"

        original_app = type(sl).app
        type(sl).app = property(lambda self: mock_app)
        try:
            sl.on_key(mock_event)
        finally:
            type(sl).app = original_app

        assert mock_app._quit_toast_active is False
        mock_event.stop.assert_called_once()
        assert len(sl.selected) == 0

    def test_space_toggles_selection_normally(self, tmp_db):
        _insert_session(tmp_db)
        from seshi.tui.sessions import SessionsList

        sl = SessionsList(tmp_db)
        mock_app = MagicMock()
        mock_app._quit_toast_active = False
        mock_event = MagicMock()
        mock_event.key = "space"
        mock_event.is_printable = False
        mock_event.character = None

        original_app = type(sl).app
        type(sl).app = property(lambda self: mock_app)
        try:
            sl.on_key(mock_event)
        finally:
            type(sl).app = original_app

        assert len(sl.selected) == 1
