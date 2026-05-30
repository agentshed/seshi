"""Tests for UX enhancement issues #2, #42, #44, #45, #46, #47."""
import time
from unittest.mock import patch, PropertyMock

from textual.geometry import Size

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
    from seshi.session_index import index_session_search
    index_session_search(conn, session_id)
    conn.commit()


# === #2: Stale session filtering ===

def test_get_existing_session_ids(tmp_path):
    from seshi.transcript import get_existing_session_ids
    from seshi.paths import CLAUDE_PROJECTS
    import unittest.mock as mock

    project = tmp_path / "test-project"
    project.mkdir()
    sid = "aaaaaaaa-bbbb-cccc-dddd-111111111111"
    (project / f"{sid}.jsonl").write_text("{}\n")
    (project / "not-a-uuid.jsonl").write_text("{}\n")

    with mock.patch("seshi.transcript.CLAUDE_PROJECTS", tmp_path):
        ids = get_existing_session_ids()

    assert sid in ids
    assert "not-a-uuid" not in ids


def test_hide_stale_sessions_setting(tmp_db):
    from seshi.db import set_setting, get_setting
    set_setting(tmp_db, "hide_stale_sessions", "1")
    assert get_setting(tmp_db, "hide_stale_sessions") == "1"


# === #44: Empty state messages ===

def test_empty_state_no_sessions(tmp_db):
    view = SessionsList(tmp_db)
    rendered = view.render().plain
    assert "No sessions yet" in rendered
    assert "seshi scan" in rendered


def test_empty_state_search_no_match(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="auth-rewrite")
    view = SessionsList(tmp_db)
    view._current_query = "zzzznonexistent"
    view._load_sessions(query="zzzznonexistent")
    rendered = view.render().plain
    assert "No sessions match" in rendered


def test_empty_state_filter_cwd(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/tmp/a")
    view = SessionsList(tmp_db)
    view.filter_cwd = "/tmp/nonexistent"
    view._load_sessions()
    rendered = view.render().plain
    assert "No sessions for this project" in rendered


# === #45: Search match highlighting ===

def test_search_highlighting_present(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="auth-rewrite")
    view = SessionsList(tmp_db)
    view._current_query = "auth"
    view._load_sessions(query="auth")
    rendered = view.render()
    spans = rendered._spans
    has_highlight = any("underline" in str(s.style) for s in spans)
    assert has_highlight


# === #42: Footer keybindings ===

def _render_footer(view_name, width=200):
    from seshi.tui.footer import Footer
    footer = Footer()
    footer.view = view_name
    with patch.object(type(footer), "size", new_callable=PropertyMock, return_value=Size(width, 1)):
        return footer.render().plain


def test_footer_shows_search_key():
    rendered = _render_footer("sessions")
    assert "/" in rendered
    assert "search" in rendered


def test_footer_shows_help_key():
    rendered = _render_footer("sessions")
    assert "?" in rendered
    assert "help" in rendered


def test_footer_shows_hide_key():
    rendered = _render_footer("sessions")
    assert "H" in rendered
    assert "hide" in rendered


def test_footer_shows_preview_key():
    rendered = _render_footer("sessions")
    assert "preview" in rendered


def test_footer_projects_shows_nav():
    rendered = _render_footer("projects")
    assert "g/G" in rendered


def test_footer_overview_shows_scroll():
    rendered = _render_footer("overview")
    assert "scroll" in rendered


# === #46/#47: View consistency ===

def test_projects_g_jumps_to_top(tmp_db):
    for i in range(5):
        _insert_session(tmp_db, f"s{i}", cwd=f"/tmp/p{i}")
    from seshi.tui.projects import ProjectsView
    view = ProjectsView(tmp_db)
    view.cursor = 3
    from unittest.mock import MagicMock
    event = MagicMock()
    event.key = "g"
    view.on_key(event)
    assert view.cursor == 0


def test_projects_G_jumps_to_bottom(tmp_db):
    for i in range(5):
        _insert_session(tmp_db, f"s{i}", cwd=f"/tmp/p{i}")
    from seshi.tui.projects import ProjectsView
    view = ProjectsView(tmp_db)
    view.cursor = 0
    from unittest.mock import MagicMock
    event = MagicMock()
    event.key = "G"
    view.on_key(event)
    assert view.cursor == len(view._projects) - 1


# === #44: Projects empty state ===

def test_projects_empty_state(tmp_db):
    from seshi.tui.projects import ProjectsView
    view = ProjectsView(tmp_db)
    rendered = view.render().plain
    assert "No projects found" in rendered
    assert "seshi scan" in rendered


# === Help text updated ===

def test_help_text_updated():
    from seshi.tui.help_view import HELP_TEXT
    assert "Ctrl-a" in HELP_TEXT
    assert "confirmation" in HELP_TEXT.lower()
    assert "preview" in HELP_TEXT.lower()
    assert "stale" in HELP_TEXT.lower()
