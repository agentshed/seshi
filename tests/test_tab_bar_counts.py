"""Tests for session/project counts in tab bar."""
import time
from unittest.mock import MagicMock, PropertyMock, patch

from seshi.tui.app import SeshiApp


def _insert_session(conn, session_id, cwd="/tmp/project", ts=None):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json,
         created_at, last_activity_at)
        VALUES (?,?,?,?,?)""",
        (session_id, cwd, "[]", ts, ts),
    )
    conn.commit()


def test_tab_bar_shows_session_count(tmp_db):
    for i in range(5):
        _insert_session(tmp_db, f"s{i}")
    app = SeshiApp(conn=tmp_db)
    mock_sessions = MagicMock()
    mock_sessions._all_sessions = list(range(5))
    app._sessions_list = mock_sessions
    mock_static = MagicMock()
    with patch.object(app, 'query_one', return_value=mock_static):
        app._update_tab_bar()
    rendered = mock_static.update.call_args[0][0].plain
    assert "5" in rendered


def test_tab_bar_shows_project_count(tmp_db):
    for i in range(3):
        _insert_session(tmp_db, f"s{i}", cwd=f"/tmp/proj{i}")
    app = SeshiApp(conn=tmp_db)
    mock_sessions = MagicMock()
    mock_sessions._all_sessions = []
    app._sessions_list = mock_sessions
    mock_static = MagicMock()
    with patch.object(app, 'query_one', return_value=mock_static):
        app._update_tab_bar()
    rendered = mock_static.update.call_args[0][0].plain
    assert "3" in rendered  # 3 distinct projects


def test_tab_bar_zero_counts(tmp_db):
    app = SeshiApp(conn=tmp_db)
    mock_sessions = MagicMock()
    mock_sessions._all_sessions = []
    app._sessions_list = mock_sessions
    mock_static = MagicMock()
    with patch.object(app, 'query_one', return_value=mock_static):
        app._update_tab_bar()
    rendered = mock_static.update.call_args[0][0].plain
    assert "0" in rendered


def test_get_project_count(tmp_db):
    for i in range(4):
        _insert_session(tmp_db, f"s{i}", cwd=f"/tmp/proj{i % 2}")
    app = SeshiApp(conn=tmp_db)
    count = app._get_project_count()
    assert count == 2  # 2 distinct cwds


def test_get_project_count_excludes_archived(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/tmp/active")
    _insert_session(tmp_db, "s2", cwd="/tmp/archived")
    tmp_db.execute("UPDATE sessions SET is_archived = 1 WHERE session_id = 's2'")
    tmp_db.commit()
    app = SeshiApp(conn=tmp_db)
    count = app._get_project_count()
    assert count == 1


def test_tab_bar_contains_sessions_label(tmp_db):
    app = SeshiApp(conn=tmp_db)
    mock_sessions = MagicMock()
    mock_sessions._all_sessions = []
    app._sessions_list = mock_sessions
    mock_static = MagicMock()
    with patch.object(app, 'query_one', return_value=mock_static):
        app._update_tab_bar()
    rendered = mock_static.update.call_args[0][0].plain
    assert "sessions" in rendered
    assert "projects" in rendered
    assert "help" in rendered
