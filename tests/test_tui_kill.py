"""Tests for the Kill session (Shift-K) feature."""
import sqlite3
import subprocess
from unittest.mock import patch, MagicMock

from seshi.db import init_schema, set_setting
from seshi.live import LiveInfo
from seshi.models import Session
from seshi.tui.sessions import SessionsList


def _make_session(sid="a0b1c2d3-0000-0000-0000-000000000000", cwd="/tmp/proj",
                  name=None, fav=0, prompt=None):
    return Session(
        session_id=sid, cwd=cwd, launch_argv_json="[]", env_json=None,
        git_branch=None, git_sha=None, first_prompt=prompt,
        custom_name=name, ai_title=None,
        is_favorite=fav, is_archived=0, is_backfilled=0,
        message_count=10, token_count=500, status="done",
        created_at=1000, last_activity_at=2000,
        origin_host=None, schema_version=0,
    )


def _make_live(sid="a0b1c2d3-0000-0000-0000-000000000000", status="busy",
               kind="background", detail=None, cwd="/tmp/proj", name=None):
    return LiveInfo(
        session_id=sid, pid=123, kind=kind, status=status,
        detail=detail, name=name, daemon_short=sid[:8], cwd=cwd,
    )


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    set_setting(conn, "hide_stale_sessions", "0")
    return conn


def _insert_session(conn, session):
    conn.execute(
        """INSERT OR IGNORE INTO sessions
        (session_id, cwd, launch_argv_json, env_json, git_branch, git_sha,
         first_prompt, custom_name, ai_title, is_favorite, is_archived,
         is_backfilled, message_count, token_count, status,
         created_at, last_activity_at, origin_host, schema_version,
         resume_count, frecency_rank)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (session.session_id, session.cwd, session.launch_argv_json,
         session.env_json, session.git_branch, session.git_sha,
         session.first_prompt, session.custom_name, session.ai_title,
         session.is_favorite, session.is_archived, session.is_backfilled,
         session.message_count, session.token_count, session.status,
         session.created_at, session.last_activity_at, session.origin_host,
         session.schema_version, session.resume_count, session.frecency_rank),
    )
    conn.commit()


def _setup_widget(conn):
    sl = SessionsList(conn)
    sl._notify = lambda msg, **kw: sl._test_notifications.append((msg, kw))
    sl._test_notifications = []
    return sl


# ── Kill live session stops ────────────────────────────────────────

def test_kill_live_session_stops():
    conn = _make_conn()
    s = _make_session(name="live session")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()

    with patch.object(sl, "_run_claude_cmd") as mock_cmd:
        mock_cmd.return_value = MagicMock(returncode=0, stderr="")
        sl._kill_selected()

    mock_cmd.assert_called_once_with("stop", s.session_id[:8])
    assert s.session_id in sl._stopped_sessions
    assert any("press K again" in msg.lower() or "stopped" in msg.lower()
               for msg, _ in sl._test_notifications)


# ── Kill stopped session removes worktree ──────────────────────────

def test_kill_stopped_session_removes():
    conn = _make_conn()
    s = _make_session(name="stopped session")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {}
    sl._stopped_sessions[s.session_id] = s.session_id[:8]
    sl._refresh_display()

    with patch.object(sl, "_run_claude_cmd") as mock_cmd:
        mock_cmd.return_value = MagicMock(returncode=0, stderr="")
        sl._kill_selected()

    mock_cmd.assert_called_once_with("rm", s.session_id[:8])
    assert s.session_id not in sl._stopped_sessions
    assert any("removed" in msg.lower() or "worktree" in msg.lower()
               for msg, _ in sl._test_notifications)


# ── Kill non-live session notifies ─────────────────────────────────

def test_kill_non_live_session_notifies():
    conn = _make_conn()
    s = _make_session(name="old session")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {}
    sl._refresh_display()

    sl._kill_selected()

    assert len(sl._test_notifications) == 1
    assert "not running" in sl._test_notifications[0][0].lower()


# ── Kill stop failure handling ─────────────────────────────────────

def test_kill_stop_failure_handling():
    conn = _make_conn()
    s = _make_session(name="failing session")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()

    with patch.object(sl, "_run_claude_cmd") as mock_cmd:
        mock_cmd.return_value = MagicMock(returncode=1, stderr="process not found")
        sl._kill_selected()

    assert s.session_id not in sl._stopped_sessions
    assert len(sl._test_notifications) == 1
    assert "failed" in sl._test_notifications[0][0].lower()


# ── Kill rm failure handling ───────────────────────────────────────

def test_kill_rm_failure_handling():
    conn = _make_conn()
    s = _make_session(name="rm fail session")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {}
    sl._stopped_sessions[s.session_id] = s.session_id[:8]
    sl._refresh_display()

    with patch.object(sl, "_run_claude_cmd") as mock_cmd:
        mock_cmd.return_value = MagicMock(returncode=1, stderr="worktree not found")
        sl._kill_selected()

    assert s.session_id in sl._stopped_sessions
    assert len(sl._test_notifications) == 1
    assert "failed" in sl._test_notifications[0][0].lower()


# ── Kill with subprocess exception ─────────────────────────────────

def test_kill_subprocess_exception():
    conn = _make_conn()
    s = _make_session(name="exception session")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()

    with patch.object(sl, "_run_claude_cmd") as mock_cmd:
        mock_cmd.side_effect = FileNotFoundError("claude not found")
        sl._kill_selected()

    assert s.session_id not in sl._stopped_sessions
    assert len(sl._test_notifications) == 1
    assert "failed" in sl._test_notifications[0][0].lower()


# ── Stopped sessions reconciled on live state update ──────────────

def test_stopped_sessions_pruned_on_live_refresh():
    conn = _make_conn()
    s = _make_session(name="restarted session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl._stopped_sessions[s.session_id] = s.session_id[:8]

    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()

    assert s.session_id not in sl._stopped_sessions


# ── Invalid daemon_short rejected ─────────────────────────────────

def test_kill_invalid_daemon_short():
    conn = _make_conn()
    s = _make_session(sid="XXXX!!!!-0000-0000-0000-000000000000", name="bad id")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()

    with patch.object(sl, "_run_claude_cmd") as mock_cmd:
        sl._kill_selected()

    mock_cmd.assert_not_called()
    assert len(sl._test_notifications) == 1
    assert "invalid" in sl._test_notifications[0][0].lower()


# ── _run_claude_cmd calls subprocess correctly ─────────────────────

def test_run_claude_cmd():
    conn = _make_conn()
    sl = SessionsList(conn)

    with patch("seshi.tui.sessions.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = sl._run_claude_cmd("stop", "abcd1234")

    mock_run.assert_called_once_with(
        ["claude", "stop", "abcd1234"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
