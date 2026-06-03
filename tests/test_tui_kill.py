"""Tests for the Kill session (Shift-K) feature."""
from unittest.mock import patch, MagicMock

from seshi.live import LiveInfo
from seshi.tui.sessions import SessionsList

from tests.helpers import make_session, make_live, make_conn, insert_session


def _setup_widget(conn):
    sl = SessionsList(conn)
    sl._test_notifications = []
    sl._notify = lambda msg, **kw: sl._test_notifications.append((msg, kw))
    return sl


# ── _on_kill_stopped updates state and notifies ───────────────────

def test_on_kill_stopped():
    conn = make_conn()
    sl = _setup_widget(conn)

    sl._on_kill_stopped("abc12345-sid", "abc12345")

    assert sl._stopped_sessions["abc12345-sid"] == "abc12345"
    assert any("press K again" in msg.lower() or "stopped" in msg.lower()
               for msg, _ in sl._test_notifications)


# ── _on_kill_removed cleans up state ─────────────────────────────

def test_on_kill_removed():
    conn = make_conn()
    sl = _setup_widget(conn)
    sl._stopped_sessions["abc12345-sid"] = "abc12345"
    sl.live_states["abc12345-sid"] = make_live("abc12345-sid")

    sl._on_kill_removed("abc12345-sid")

    assert "abc12345-sid" not in sl._stopped_sessions
    assert "abc12345-sid" not in sl.live_states
    assert any("removed" in msg.lower() or "worktree" in msg.lower()
               for msg, _ in sl._test_notifications)


# ── Kill non-live session notifies ────────────────────────────────

def test_kill_non_live_session_notifies():
    conn = make_conn()
    s = make_session(name="old session")
    insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {}
    sl._refresh_display()

    sl._kill_selected()

    assert len(sl._test_notifications) == 1
    assert "not running" in sl._test_notifications[0][0].lower()


# ── Kill dispatches worker for live session ───────────────────────

def test_kill_dispatches_worker_for_live():
    conn = make_conn()
    s = make_session(name="live session")
    insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {s.session_id: make_live(s.session_id)}
    sl._refresh_display()

    with patch.object(sl, "run_worker") as mock_worker:
        sl._kill_selected()

    mock_worker.assert_called_once()
    assert mock_worker.call_args.kwargs.get("thread") is True


# ── Kill dispatches worker for stopped session ────────────────────

def test_kill_dispatches_worker_for_stopped():
    conn = make_conn()
    s = make_session(name="stopped session")
    insert_session(conn, s)
    sl = _setup_widget(conn)
    sl._stopped_sessions[s.session_id] = s.session_id[:8]
    # Session still in live_states (transitioning) so pruning doesn't remove it
    sl.live_states = {s.session_id: make_live(s.session_id)}
    sl._refresh_display()

    with patch.object(sl, "run_worker") as mock_worker:
        sl._kill_selected()

    mock_worker.assert_called_once()
    assert mock_worker.call_args.kwargs.get("thread") is True


# ── In-flight guard prevents duplicate dispatch ──────────────────

def test_kill_in_flight_guard():
    conn = make_conn()
    s = make_session(name="in-flight session")
    insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {s.session_id: make_live(s.session_id)}
    sl._kill_in_flight.add(s.session_id)
    sl._refresh_display()

    with patch.object(sl, "run_worker") as mock_worker:
        sl._kill_selected()

    mock_worker.assert_not_called()


# ── Stopped sessions preserved when still transitioning ───────────

def test_stopped_sessions_preserved_while_still_live():
    """Stopped session kept when still in live_states with same daemon_short."""
    conn = make_conn()
    s = make_session(name="recently stopped session")
    insert_session(conn, s)
    sl = SessionsList(conn)
    sl._stopped_sessions[s.session_id] = s.session_id[:8]

    sl.live_states = {s.session_id: make_live(s.session_id)}
    sl._refresh_display()

    assert s.session_id in sl._stopped_sessions


# ── Stopped sessions pruned when fully disappeared from live ──────

def test_stopped_sessions_pruned_when_not_live():
    """Stopped session removed once it disappears from live_states."""
    conn = make_conn()
    s = make_session(name="gone session")
    insert_session(conn, s)
    sl = SessionsList(conn)
    sl._stopped_sessions[s.session_id] = s.session_id[:8]

    sl.live_states = {}  # session no longer live
    sl._refresh_display()

    assert s.session_id not in sl._stopped_sessions


# ── Stopped session cleared when relaunched with new daemon ───────

def test_stopped_session_cleared_on_relaunch():
    """If a stopped session reappears live with a new daemon_short, clear stopped state."""
    conn = make_conn()
    s = make_session(name="relaunched session")
    insert_session(conn, s)
    sl = SessionsList(conn)
    sl._stopped_sessions[s.session_id] = "aa000001"

    # Reappears with a different daemon_short
    new_live = LiveInfo(
        session_id=s.session_id, pid=456, kind="background", status="busy",
        detail=None, name=None, daemon_short="bb000002", cwd="/tmp/proj",
    )
    sl.live_states = {s.session_id: new_live}
    sl._refresh_display()

    assert s.session_id not in sl._stopped_sessions


# ── Invalid daemon_short rejected ─────────────────────────────────

def test_kill_invalid_daemon_short():
    conn = make_conn()
    s = make_session(sid="XXXX!!!!-0000-0000-0000-000000000000", name="bad id")
    insert_session(conn, s)
    sl = _setup_widget(conn)
    sl.live_states = {s.session_id: make_live(s.session_id)}
    sl._refresh_display()

    with patch.object(sl, "run_worker") as mock_worker:
        sl._kill_selected()

    mock_worker.assert_not_called()
    assert len(sl._test_notifications) == 1
    assert "invalid" in sl._test_notifications[0][0].lower()


# ── _run_claude_cmd calls subprocess correctly ─────────────────────

def test_run_claude_cmd():
    conn = make_conn()
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
    conn = make_conn()
    sl = SessionsList(conn)

    assert sl._resolve_daemon_short("a0b1c2d3-rest-of-uuid") == "a0b1c2d3"


def test_resolve_daemon_short_invalid():
    conn = make_conn()
    sl = SessionsList(conn)

    assert sl._resolve_daemon_short("XXXX!!!!-rest") is None


def test_resolve_daemon_short_uses_live():
    conn = make_conn()
    sl = SessionsList(conn)
    sl.live_states = {"a0b1c2d3-uuid": make_live("a0b1c2d3-uuid")}

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
    conn = make_conn()
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
    conn = make_conn()
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
    conn = make_conn()
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
    conn = make_conn()
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
    conn = make_conn()
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


# ── Stale daemon_short race: _kill_selected re-routes to stop ─────

def test_kill_stale_daemon_reroutes_to_stop():
    """When _stopped_sessions has an old daemon_short but live_states has a
    new one, _kill_selected should clear stopped state and dispatch stop
    (not rm) for the new daemon.

    This simulates the race where _refresh_display() has NOT yet run after
    the session was relaunched — the stale entry is still in _stopped_sessions
    when the user presses K.
    """
    conn = make_conn()
    s = make_session(name="relaunched")
    insert_session(conn, s)
    sl = _setup_widget(conn)

    # Build display rows first with original live state so cursor is valid
    sl.live_states = {s.session_id: make_live(s.session_id)}
    sl._refresh_display()

    # Now simulate the race: session relaunched with a new daemon_short,
    # but _refresh_display() has NOT run yet, so _stopped_sessions still
    # has the old daemon_short.
    sl._stopped_sessions[s.session_id] = "aa000001"
    new_live = LiveInfo(
        session_id=s.session_id, pid=789, kind="background", status="busy",
        detail=None, name=None, daemon_short="bb000002", cwd="/tmp/proj",
    )
    sl.live_states = {s.session_id: new_live}

    with patch.object(sl, "run_worker") as mock_worker:
        sl._kill_selected()

    # Stopped state should be cleared (not used for rm)
    assert s.session_id not in sl._stopped_sessions
    # Worker should be dispatched (for stop, not rm)
    mock_worker.assert_called_once()
    assert mock_worker.call_args.kwargs.get("thread") is True
    # Extract the lambda and verify it would call "stop" not "rm"
    worker_fn = mock_worker.call_args.args[0]
    with patch.object(sl, "_do_kill") as mock_do_kill:
        worker_fn()
    mock_do_kill.assert_called_once_with("stop", s.session_id, "bb000002")
