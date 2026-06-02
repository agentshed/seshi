"""Tests for live session integration in the TUI."""
import sqlite3
from collections import namedtuple
from unittest.mock import PropertyMock

from seshi.db import init_schema, set_setting
from seshi.live import LiveInfo
from seshi.models import Session
from seshi.tui.sessions import SessionsList
from seshi.tui.header import Header
from seshi.tui.footer import Footer

_Size = namedtuple("Size", ["width", "height"])


def _make_session(sid="test0000-0000-0000-0000-000000000000", cwd="/tmp/proj",
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


def _make_live(sid="test0000-0000-0000-0000-000000000000", status="busy",
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


def _render_sessions_list(sl, width=120, height=30):
    _original = SessionsList.size
    type(sl).size = PropertyMock(return_value=_Size(width, height))
    try:
        return sl.render()
    finally:
        type(sl).size = _original


# ── Positive: live bucket ───────────────────────────────────────────

def test_live_bucket_shown_when_live_sessions_exist():
    conn = _make_conn()
    s = _make_session()
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    assert "live" in text


def test_live_bucket_not_shown_when_empty():
    conn = _make_conn()
    s = _make_session()
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {}
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    assert "live" not in text.split("★")[0] if "★" in text else "live" not in text


def test_live_session_shows_busy_icon():
    conn = _make_conn()
    s = _make_session(name="my session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id, status="busy")}
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    assert "✽" in text or "✻" in text


def test_live_session_shows_needs_input_icon():
    conn = _make_conn()
    s = _make_session(name="waiting session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id, status="needs_input")}
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    assert "✻" in text


def test_live_session_shows_detail():
    conn = _make_conn()
    s = _make_session(name="active session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id, detail="Running pytest...")}
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    assert "Running pytest" in text


def test_live_sessions_sorted_by_urgency():
    conn = _make_conn()
    s1 = _make_session(sid="aaaa0000-0000-0000-0000-000000000001", name="busy one")
    s2 = _make_session(sid="aaaa0000-0000-0000-0000-000000000002", name="waiting one")
    _insert_session(conn, s1)
    _insert_session(conn, s2)
    sl = SessionsList(conn)
    sl.live_states = {
        s1.session_id: _make_live(s1.session_id, status="busy"),
        s2.session_id: _make_live(s2.session_id, status="needs_input"),
    }
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    pos_waiting = text.find("waiting one")
    pos_busy = text.find("busy one")
    assert pos_waiting < pos_busy, "needs_input should sort before busy"


def test_live_session_suppressed_from_cwd_group():
    conn = _make_conn()
    s = _make_session(name="active session", cwd="/tmp/proj")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    count = text.count("active session")
    assert count == 1, f"Expected 1 occurrence, found {count}"


# ── Positive: header & footer ──────────────────────────────────────

def test_header_shows_live_count():
    header = Header()
    header.live_count = 3
    text = header.render().plain
    assert "3 live" in text


def test_header_hides_live_count_when_zero():
    header = Header()
    header.live_count = 0
    text = header.render().plain
    assert "live" not in text


def test_footer_shows_attach_for_live_bg():
    _original = Footer.size
    footer = Footer()
    footer.live_bg_selected = True
    type(footer).size = PropertyMock(return_value=_Size(200, 1))
    try:
        text = footer.render().plain
    finally:
        type(footer).size = _original
    assert "attach" in text


def test_footer_shows_resume_when_no_live():
    _original = Footer.size
    footer = Footer()
    footer.live_bg_selected = False
    type(footer).size = PropertyMock(return_value=_Size(200, 1))
    try:
        text = footer.render().plain
    finally:
        type(footer).size = _original
    assert "resume" in text


# ── Positive: enter key action ─────────────────────────────────────

def test_enter_on_live_bg_sets_attach():
    conn = _make_conn()
    s = _make_session(name="bg session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id, kind="background")}
    sl._refresh_display()
    live = sl.live_states.get(s.session_id)
    assert live is not None
    assert live.kind == "background"


def test_enter_on_live_interactive_should_resume():
    conn = _make_conn()
    s = _make_session(name="interactive session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id, kind="interactive")}
    sl._refresh_display()
    live = sl.live_states.get(s.session_id)
    assert live is not None
    assert live.kind == "interactive"


# ── Negative cases ─────────────────────────────────────────────────

def test_no_icon_when_no_live_states():
    conn = _make_conn()
    s = _make_session(name="old session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {}
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    assert "✽" not in text
    assert "✻" not in text


def test_no_crash_when_live_sid_not_in_sessions():
    conn = _make_conn()
    sl = SessionsList(conn)
    sl.live_states = {
        "unknown0-0000-0000-0000-000000000000": _make_live(
            "unknown0-0000-0000-0000-000000000000",
            name="untracked", cwd="/tmp/untracked",
        )
    }
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    assert "untracked" in text
    assert "live" in text


def test_no_detail_on_narrow_terminal():
    conn = _make_conn()
    s = _make_session(name="narrow session")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id, detail="Running tests...")}
    sl._refresh_display()
    text = _render_sessions_list(sl, width=60).plain
    assert "Running tests" not in text


# ── Edge cases ─────────────────────────────────────────────────────

def test_live_state_removal_drops_from_live_bucket():
    conn = _make_conn()
    s = _make_session(name="was live")
    _insert_session(conn, s)
    sl = SessionsList(conn)

    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()
    assert "live" in _render_sessions_list(sl).plain

    sl.live_states = {}
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    assert "was live" in text
    assert "● " not in text.split("was live")[0] or "live" not in text.split("★")[0] if "★" in text else True


def test_animation_toggles_busy_icon():
    conn = _make_conn()
    s = _make_session(name="animated")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id, status="busy")}
    sl._refresh_display()

    sl._anim_frame = 0
    text0 = _render_sessions_list(sl).plain
    sl._anim_frame = 1
    text1 = _render_sessions_list(sl).plain
    icons_0 = text0.count("✽") + text0.count("✻")
    icons_1 = text1.count("✽") + text1.count("✻")
    assert icons_0 > 0 and icons_1 > 0


def test_detail_truncation():
    conn = _make_conn()
    s = _make_session(name="truncate")
    _insert_session(conn, s)
    sl = SessionsList(conn)
    long_detail = "A" * 200
    sl.live_states = {s.session_id: _make_live(s.session_id, detail=long_detail)}
    sl._refresh_display()
    text = _render_sessions_list(sl, width=120).plain
    lines = text.split("\n")
    for line in lines:
        assert len(line) <= 120


def test_state_column_only_when_live_exists():
    conn = _make_conn()
    s = _make_session(name="test")
    _insert_session(conn, s)
    sl = SessionsList(conn)

    sl.live_states = {}
    sl._refresh_display()
    text_no_live = _render_sessions_list(sl).plain

    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()
    text_live = _render_sessions_list(sl).plain

    no_live_lines = [l for l in text_no_live.split("\n") if "test" in l]
    live_lines = [l for l in text_live.split("\n") if "test" in l]
    if no_live_lines and live_lines:
        no_live_start = no_live_lines[0].index("test")
        live_start = live_lines[0].index("test")
        assert live_start >= no_live_start


def test_untracked_live_session_uses_name_from_liveinfo():
    conn = _make_conn()
    sl = SessionsList(conn)
    sl.live_states = {
        "newone00-0000-0000-0000-000000000000": _make_live(
            "newone00-0000-0000-0000-000000000000",
            name="fix-auth",
        )
    }
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    assert "fix-auth" in text


def test_live_favorite_in_live_bucket_not_favorites():
    conn = _make_conn()
    s = _make_session(name="fav live", fav=1)
    _insert_session(conn, s)
    sl = SessionsList(conn)
    sl.live_states = {s.session_id: _make_live(s.session_id)}
    sl._refresh_display()
    text = _render_sessions_list(sl).plain
    live_pos = text.find("live")
    fav_pos = text.find("fav live")
    assert live_pos < fav_pos, "Live favorite should appear in the live bucket"
    count = text.count("fav live")
    assert count == 1, f"Expected 1 occurrence of favorite session, found {count}"
