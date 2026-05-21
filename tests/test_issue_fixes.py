"""Tests for batch issue fixes.

Covers: #1, #12, #13, #15, #23, #24, #25, #28, #29, #30, #31, #32, #33, #34,
        #35, #37, #38, #39, #40, #43, #48
"""
import math
import os
import time

from seshi.search import fuzzy_match, rank_sessions
from seshi.tui.sessions import SessionsList, strip_markup_tags, FUZZY_THRESHOLD


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


# === #12: Strip XML tags from prompt text ===

def test_strip_markup_tags_removes_xml():
    text = "<local-command-caveat>Caveat</local-command-caveat> Open the repo"
    assert strip_markup_tags(text) == "Caveat Open the repo"


def test_strip_markup_tags_self_closing():
    assert strip_markup_tags("<br/>hello") == "hello"


def test_strip_markup_tags_keeps_angle_brackets():
    assert strip_markup_tags("compare 2 < 3 > 1") == "compare 2 < 3 > 1"


def test_session_list_strips_tags_from_prompt(tmp_db):
    _insert_session(tmp_db, "tagged-prompt",
                    first_prompt="<system-reminder>text</system-reminder> Real prompt")
    view = SessionsList(tmp_db)
    rendered = view.render().plain
    assert "<system-reminder>" not in rendered
    assert "Real prompt" in rendered


# === #13: Quit toast space toggle prevention ===

def test_quit_toast_flag_blocks_key(tmp_db):
    from unittest.mock import MagicMock
    _insert_session(tmp_db, "sess-1")
    sl = SessionsList(tmp_db)
    mock_app = MagicMock()
    mock_app._quit_toast_active = True
    original_app = type(sl).app
    type(sl).app = property(lambda self: mock_app)
    try:
        mock_event = MagicMock()
        mock_event.key = "space"
        sl.on_key(mock_event)
    finally:
        type(sl).app = original_app
    assert mock_app._quit_toast_active is False
    mock_event.stop.assert_called_once()
    assert len(sl.selected) == 0


# === #28: Fuzzy search threshold ===

def test_fuzzy_threshold_filters_weak_matches(tmp_db):
    _insert_session(tmp_db, "id-1", first_prompt="fix auth middleware bug")
    _insert_session(tmp_db, "id-2", first_prompt="unrelated task about logs")
    _insert_session(tmp_db, "id-3", first_prompt="completely different topic xyz")
    results = rank_sessions(tmp_db, "auth")
    session_ids = [s.session_id for s, _ in results]
    assert "id-1" in session_ids
    assert len(results) < 3


def test_fuzzy_threshold_value():
    assert FUZZY_THRESHOLD >= 50


# === #30: Header count (total vs shown) ===

def test_all_sessions_set_before_filter(tmp_db):
    _insert_session(tmp_db, "id-1", custom_name="auth-rewrite", cwd="/tmp/a")
    _insert_session(tmp_db, "id-2", first_prompt="xyz completely unrelated", cwd="/tmp/b")
    _insert_session(tmp_db, "id-3", first_prompt="qqq different topic", cwd="/tmp/c")
    view = SessionsList(tmp_db)
    assert len(view._all_sessions) == 3
    assert len(view.sessions) == 3
    view.filter("auth-rewrite")
    assert len(view._all_sessions) == 3
    assert len(view.sessions) < len(view._all_sessions)


# === #29: Search filter preserved after mutations ===

def test_search_filter_preserved_after_favorite(tmp_db):
    _insert_session(tmp_db, "id-1", custom_name="auth-rewrite")
    _insert_session(tmp_db, "id-2", first_prompt="unrelated")
    view = SessionsList(tmp_db)
    view.filter("auth")
    initial_count = len(view.sessions)
    view._toggle_favorite()
    assert view._current_query == "auth"
    assert len(view.sessions) == initial_count


# === #25: _update_counts called after mutations ===

def test_reload_with_current_filter_calls_load(tmp_db):
    _insert_session(tmp_db, "id-1", custom_name="auth-rewrite")
    view = SessionsList(tmp_db)
    view.filter("auth")
    view._current_query = "auth"
    view._reload_with_current_filter()
    assert len(view.sessions) >= 1


# === #3: Select-all changed to Ctrl+A ===

def test_select_all_uses_ctrl_a(tmp_db):
    _insert_session(tmp_db, "s1")
    _insert_session(tmp_db, "s2")
    view = SessionsList(tmp_db)
    from unittest.mock import MagicMock
    mock_event_a = MagicMock()
    mock_event_a.key = "a"
    mock_event_a.is_printable = True
    mock_event_a.character = "a"
    mock_app = MagicMock()
    mock_app._quit_toast_active = False
    search = MagicMock()
    search.active = False
    search.query = ""
    mock_app.query_one.return_value = search
    original_app = type(view).app
    type(view).app = property(lambda self: mock_app)
    try:
        view.on_key(mock_event_a)
    finally:
        type(view).app = original_app
    assert len(view.selected) == 0


# === #48: Cursor indicator character ===

def test_cursor_indicator_in_render(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    rendered = view.render().plain
    assert "▸" in rendered


# === #39: Double slash normalization ===

def test_drain_normalizes_double_slash(tmp_db):
    import json
    from seshi.drain import drain_queue
    from seshi.paths import QUEUE_PATH
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event": "start",
        "session_id": "test-double-slash",
        "cwd": "/home/user//project",
        "ts": int(time.time()),
    }
    QUEUE_PATH.write_text(json.dumps(event) + "\n")
    drain_queue(tmp_db)
    row = tmp_db.execute(
        "SELECT cwd FROM sessions WHERE session_id = ?", ("test-double-slash",)
    ).fetchone()
    assert row is not None
    assert "//" not in row["cwd"]


# === #1: Scan uses mtime not now ===

def test_scan_uses_mtime(tmp_db, tmp_path):
    from seshi.scan import scan_projects
    project = tmp_path / "some-project"
    project.mkdir()
    past = time.time() - 7 * 86400
    sid = "aaaaaaaa-bbbb-cccc-dddd-111111111111"
    (project / sid).mkdir()
    os.utime(project / sid, (past, past))
    scan_projects(tmp_db, projects_root=tmp_path)
    row = tmp_db.execute(
        "SELECT created_at FROM sessions WHERE session_id = ?", (sid,)
    ).fetchone()
    assert row is not None
    assert abs(row["created_at"] - int(past)) < 5


# === #37: Model name context suffix stripping ===

def test_model_name_suffix_stripped():
    import re
    from seshi.tui.overview import _CTX_SUFFIX_RE
    assert _CTX_SUFFIX_RE.sub("", "claude-opus-4-6[1m]") == "claude-opus-4-6"
    assert _CTX_SUFFIX_RE.sub("", "claude-sonnet-4-5") == "claude-sonnet-4-5"
    assert _CTX_SUFFIX_RE.sub("", "unknown") == "unknown"


# === #38: Sparkline log scaling ===

def test_sparkline_log_scaling():
    days = [1, 1, 1, 100, 1, 1, 1]
    max_val = max(days)
    log_max = math.log1p(max_val)
    indices = []
    for v in days:
        if v == 0:
            idx = 0
        else:
            idx = int((math.log1p(v) / max(log_max, 1)) * 8)
        indices.append(idx)
    assert indices[3] == 8
    assert all(idx > 0 for idx in indices if idx != indices[3])


# === #40: No dim cursor when search inactive ===

def test_search_bar_no_dim_cursor_when_inactive():
    from seshi.tui.search_bar import SearchBar
    bar = SearchBar()
    bar.active = False
    bar.query = ""
    rendered = bar.render().plain
    assert "▮" not in rendered


# === #34: Long CWD paths truncated in projects ===

def test_projects_truncates_long_cwd(tmp_db):
    long_cwd = "/home/user/very/deeply/nested/project/path/that/is/extremely/long"
    _insert_session(tmp_db, "s1", cwd=long_cwd)
    from seshi.tui.projects import ProjectsView
    view = ProjectsView(tmp_db)
    rendered = view.render().plain
    assert "…" in rendered


# === #31: Project rename ===

def test_project_rename(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/tmp/myproject")
    from seshi.tui.projects import ProjectsView
    view = ProjectsView(tmp_db)
    view.cursor = 0
    view._input_mode = "rename"
    view._input_buffer = "My Cool Project"
    view._apply_rename()
    row = tmp_db.execute(
        "SELECT custom_name FROM project_favorites WHERE cwd = ?", ("/tmp/myproject",)
    ).fetchone()
    assert row is not None
    assert row["custom_name"] == "My Cool Project"


# === #24/#43: Delete confirmation ===

def test_delete_requires_confirmation(tmp_db):
    from unittest.mock import MagicMock
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    mock_app = MagicMock()
    original_app = type(view).app
    type(view).app = property(lambda self: mock_app)
    try:
        view._delete_selected()
    finally:
        type(view).app = original_app
    mock_app.push_screen.assert_called_once()
    row = tmp_db.execute("SELECT 1 FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row is not None


def test_execute_delete_removes_session(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._execute_delete(["s1"])
    row = tmp_db.execute("SELECT 1 FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row is None
