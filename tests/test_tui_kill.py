"""Tests for the Kill session (Shift-K) feature."""
import sqlite3
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
    sl._test_notifications = []
    sl._notify = lambda msg, **kw: sl._test_notifications.append((msg, kw))
    return sl


# ── _on_kill_stopped updates state and notifies ───────────────────

def test_on_kill_stopped():
    conn = _make_conn()
    sl = _setup_widget(conn)

    sl._on_kill_stopped("abc12345-sid", "abc12345")

    assert sl._stopped_sessions["abc12345-sid"] == "abc12345"
    assert any("press K again" in msg.lower() or "stopped" in msg.lower()
               for msg, _ in sl._test_notifications)


# ── _on_kill_removed cleans up state ─────────────────────────────

def test_on_kill_removed():
    conn = _make_conn()
    sl = _setup_widget(conn)
    sl._stopped_sessions["abc12345-sid"] = "abc12345"
    sl.live_states["abc12345-sid"] = _make_live("abc12345-sid")

    sl._on_kill_removed("abc12345-sid")

    assert "abc12345-sid" not in sl._stopped_sessions
    assert "abc12345-sid" not in sl.live_states
    assert any("removed" in msg.lower() or "worktree" in msg.lower()
               for msg, _ in sl._test_notifications)


# ── Kill non-live session notifies ────────────────────────────────

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


# ── Kill dispatches worker for live session ───────────────────────

def test_kill_dispatches_worker_for_live():
    conn = _make_conn()
    s = _make_session(name="live session")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()

    with patch.object(sl, "run_worker") as mock_worker:
        sl._kill_selected()

    mock_worker.assert_called_once()
    assert mock_worker.call_args.kwargs.get("thread") is True


# ── Kill dispatches worker for stopped session ────────────────────

def test_kill_dispatches_worker_for_stopped():
    conn = _make_conn()
    s = _make_session(name="stopped session")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl._stopped_sessions[s.session_id] = s.session_id[:8]
    # Session still in live_states (transitioning) so pruning doesn't remove it
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()

    with patch.object(sl, "run_worker") as mock_worker:
        sl._kill_selected()

    mock_worker.assert_called_once()
    assert mock_worker.call_args.kwargs.get("thread") is True


# ── In-flight guard prevents duplicate dispatch ──────────────────

def test_kill_in_flight_guard():
    conn = _make_conn()
    s = _make_session(name="in-flight session")
    _insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._kill_in_flight.add(s.session_id)
    sl._refresh_display()

    with patch.object(sl, "run_worker") as mock_worker:
        sl._kill_selected()

    mock_worker.assert_not_called()


# ── Stopped sessions preserved when still transitioning ───────────

def test_stopped_sessions_preserved_while_still_live():
    """Stopped session kept when still in live_states with same daemon_short."""
    conn = _make_conn()
    s = _make_session(name="recently stopped session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl._stopped_sessions[s.session_id] = s.session_id[:8]

    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()

    assert s.session_id in sl._stopped_sessions


# ── Stopped sessions pruned when fully disappeared from live ──────

def test_stopped_sessions_pruned_when_not_live():
    """Stopped session removed once it disappears from live_states."""
    conn = _make_conn()
    s = _make_session(name="gone session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl._stopped_sessions[s.session_id] = s.session_id[:8]

    sl.live_states = {}  # session no longer live
    sl._refresh_display()

    assert s.session_id not in sl._stopped_sessions


# ── Stopped session cleared when relaunched with new daemon ───────

def test_stopped_session_cleared_on_relaunch():
    """If a stopped session reappears live with a new daemon_short, clear stopped state."""
    conn = _make_conn()
    s = _make_session(name="relaunched session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl._stopped_sessions[s.session_id] = "olddddd1"

    # Reappears with a different daemon_short
    new_live = _make_live(s.session_id)
    new_live = LiveInfo(
        session_id=s.session_id, pid=456, kind="background", status="busy",
        detail=None, name=None, daemon_short="newdddd2", cwd="/tmp/proj",
    )
    sl.live_states = {s.session_id: new_live}
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

    with patch.object(sl, "run_worker") as mock_worker:
        sl._kill_selected()

    mock_worker.assert_not_called()
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


# ── _resolve_daemon_short validates hex format ─────────────────────

def test_resolve_daemon_short_valid():
    conn = _make_conn()
    sl = SessionsList(conn)

    assert sl._resolve_daemon_short("a0b1c2d3-rest-of-uuid") == "a0b1c2d3"


def test_resolve_daemon_short_invalid():
    conn = _make_conn()
    sl = SessionsList(conn)

    assert sl._resolve_daemon_short("XXXX!!!!-rest") is None


def test_resolve_daemon_short_uses_live():
    conn = _make_conn()
    sl = SessionsList(conn)
    sl.live_states = {"a0b1c2d3-uuid": _make_live("a0b1c2d3-uuid")}

    result = sl._resolve_daemon_short("a0b1c2d3-uuid")
    assert result == "a0b1c2d3"


# ── _do_kill error paths clear in-flight and notify ───────────────

def _with_mock_app(sl):
    """Set up mock app via Textual's active_app context variable."""
    from textual._context import active_app
    mock = MagicMock()
    mock.call_from_thread = lambda fn, *args, **kw: fn(*args, **kw)
    token = active_app.set(mock)
    return token, active_app


def test_do_kill_stop_success():
    conn = _make_conn()
    sl = _setup_widget(conn)
    sl._kill_in_flight.add("sid1")
    token, ctx = _with_mock_app(sl)

    try:
        with patch.object(sl, "_run_claude_cmd") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0, stderr="")
            sl._do_kill("stop", "sid1", "abcd1234")
    finally:
        ctx.reset(token)

    assert "sid1" not in sl._kill_in_flight
    assert sl._stopped_sessions["sid1"] == "abcd1234"


def test_do_kill_rm_success():
    conn = _make_conn()
    sl = _setup_widget(conn)
    sl._kill_in_flight.add("sid1")
    sl._stopped_sessions["sid1"] = "abcd1234"
    token, ctx = _with_mock_app(sl)

    try:
        with patch.object(sl, "_run_claude_cmd") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0, stderr="")
            sl._do_kill("rm", "sid1", "abcd1234")
    finally:
        ctx.reset(token)

    assert "sid1" not in sl._kill_in_flight
    assert "sid1" not in sl._stopped_sessions


def test_do_kill_nonzero_exit_clears_in_flight():
    conn = _make_conn()
    sl = _setup_widget(conn)
    sl._kill_in_flight.add("sid1")
    token, ctx = _with_mock_app(sl)

    try:
        with patch.object(sl, "_run_claude_cmd") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=1, stderr="process not found")
            sl._do_kill("stop", "sid1", "abcd1234")
    finally:
        ctx.reset(token)

    assert "sid1" not in sl._kill_in_flight
    assert any("failed" in msg.lower() for msg, _ in sl._test_notifications)


def test_do_kill_timeout_clears_in_flight():
    import subprocess as sp
    conn = _make_conn()
    sl = _setup_widget(conn)
    sl._kill_in_flight.add("sid1")
    token, ctx = _with_mock_app(sl)

    try:
        with patch.object(sl, "_run_claude_cmd") as mock_cmd:
            mock_cmd.side_effect = sp.TimeoutExpired(cmd="claude stop", timeout=10)
            sl._do_kill("stop", "sid1", "abcd1234")
    finally:
        ctx.reset(token)

    assert "sid1" not in sl._kill_in_flight
    assert any("failed" in msg.lower() for msg, _ in sl._test_notifications)


def test_do_kill_file_not_found_clears_in_flight():
    conn = _make_conn()
    sl = _setup_widget(conn)
    sl._kill_in_flight.add("sid1")
    token, ctx = _with_mock_app(sl)

    try:
        with patch.object(sl, "_run_claude_cmd") as mock_cmd:
            mock_cmd.side_effect = FileNotFoundError("claude not found")
            sl._do_kill("stop", "sid1", "abcd1234")
    finally:
        ctx.reset(token)

    assert "sid1" not in sl._kill_in_flight
    assert any("failed" in msg.lower() for msg, _ in sl._test_notifications)
