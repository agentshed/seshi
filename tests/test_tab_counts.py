"""Tests for session count in tab bar (Phase B, Item 16)."""
import time
from unittest.mock import MagicMock, patch, PropertyMock

from textual.geometry import Size

from seshi.tui.app import SeshiApp


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


def _make_mock_tab_bar():
    mock = MagicMock()
    captured = {}
    def capture_update(text):
        captured["text"] = text.plain if hasattr(text, "plain") else str(text)
    mock.update = capture_update
    return mock, captured


def test_tab_bar_shows_session_count(tmp_db):
    for i in range(5):
        _insert_session(tmp_db, f"s{i}", cwd=f"/tmp/project-{i % 2}")

    from seshi.tui.sessions import SessionsList
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = SessionsList(tmp_db)
    app._palette = MagicMock()
    app._palette.accent = "#E08A5E"
    # current_view defaults to "sessions" via reactive

    mock_tab_bar, captured = _make_mock_tab_bar()
    with patch.object(app, "query_one", return_value=mock_tab_bar):
        app._update_tab_bar()

    assert "1 sessions 5" in captured["text"]


def test_tab_bar_shows_project_count(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/tmp/proj-a")
    _insert_session(tmp_db, "s2", cwd="/tmp/proj-a")
    _insert_session(tmp_db, "s3", cwd="/tmp/proj-b")
    _insert_session(tmp_db, "s4", cwd="/tmp/proj-c")

    from seshi.tui.sessions import SessionsList
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = SessionsList(tmp_db)
    app._palette = MagicMock()
    app._palette.accent = "#E08A5E"
    # current_view defaults to "sessions" via reactive

    mock_tab_bar, captured = _make_mock_tab_bar()
    with patch.object(app, "query_one", return_value=mock_tab_bar):
        app._update_tab_bar()

    assert "3 projects 3" in captured["text"]


def test_tab_bar_shows_zero_counts_when_empty(tmp_db):
    from seshi.tui.sessions import SessionsList
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = SessionsList(tmp_db)
    app._palette = MagicMock()
    app._palette.accent = "#E08A5E"
    # current_view defaults to "sessions" via reactive

    mock_tab_bar, captured = _make_mock_tab_bar()
    with patch.object(app, "query_one", return_value=mock_tab_bar):
        app._update_tab_bar()

    assert "1 sessions 0" in captured["text"]
    assert "3 projects 0" in captured["text"]


def test_tab_bar_counts_update_after_filter(tmp_db):
    for i in range(10):
        _insert_session(tmp_db, f"s{i}", cwd=f"/tmp/project-{i % 3}",
                       custom_name=f"session-{i}")

    from seshi.tui.sessions import SessionsList
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = SessionsList(tmp_db)
    app._palette = MagicMock()
    app._palette.accent = "#E08A5E"
    # current_view defaults to "sessions" via reactive

    mock_tab_bar, captured = _make_mock_tab_bar()
    with patch.object(app, "query_one", return_value=mock_tab_bar):
        app._update_tab_bar()

    assert "1 sessions 10" in captured["text"]

    app._sessions_list.filter("session-0")
    with patch.object(app, "query_one", return_value=mock_tab_bar):
        app._update_tab_bar()

    text = captured["text"]
    count_str = text.split("1 sessions ")[1].split()[0].strip("[]")
    filtered_count = int(count_str)
    assert filtered_count < 10


def test_tab_bar_preserves_existing_labels(tmp_db):
    for i in range(3):
        _insert_session(tmp_db, f"s{i}")

    from seshi.tui.sessions import SessionsList
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = SessionsList(tmp_db)
    app._palette = MagicMock()
    app._palette.accent = "#E08A5E"
    # current_view defaults to "sessions" via reactive

    mock_tab_bar, captured = _make_mock_tab_bar()
    with patch.object(app, "query_one", return_value=mock_tab_bar):
        app._update_tab_bar()

    text = captured["text"]
    assert "1 sessions" in text
    assert "2 overview" in text
    assert "3 projects" in text
    assert "? help" in text


def test_tab_bar_no_sessions_list_yet(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._palette = MagicMock()
    app._palette.accent = "#E08A5E"
    # current_view defaults to "sessions" via reactive

    mock_tab_bar, captured = _make_mock_tab_bar()
    with patch.object(app, "query_one", return_value=mock_tab_bar):
        app._update_tab_bar()

    assert "1 sessions 0" in captured["text"]


def test_update_counts_refreshes_tab_bar(tmp_db):
    for i in range(5):
        _insert_session(tmp_db, f"s{i}")

    from seshi.tui.sessions import SessionsList
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = SessionsList(tmp_db)
    app._palette = MagicMock()
    app._palette.accent = "#E08A5E"
    # current_view defaults to "sessions" via reactive

    mock_header = MagicMock()
    mock_search = MagicMock()
    mock_tab_bar, captured = _make_mock_tab_bar()

    def query_one_side_effect(selector, *args):
        from seshi.tui.header import Header
        from seshi.tui.search_bar import SearchBar
        if selector is Header or (isinstance(selector, str) and selector == "#header"):
            return mock_header
        if selector is SearchBar or (isinstance(selector, str) and selector == "#search-bar"):
            return mock_search
        return mock_tab_bar

    with patch.object(app, "query_one", side_effect=query_one_side_effect):
        app._update_counts()

    assert "1 sessions 5" in captured["text"]
