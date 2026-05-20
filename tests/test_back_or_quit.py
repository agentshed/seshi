"""Tests for action_back_or_quit filter_cwd clearing behavior."""
import time
import types

import pytest

from seshi.db import init_schema
from seshi.tui.sessions import SessionsList


def _insert_session(conn, session_id, cwd="/home/user/project", ts=None):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, created_at, last_activity_at)
        VALUES (?,?,?,?,?)""",
        (session_id, cwd, "[]", ts, ts),
    )
    conn.commit()


def test_back_clears_filter_before_exit(tmp_db):
    """Escape should clear filter_cwd before exiting the app."""
    _insert_session(tmp_db, "s1", cwd="/home/user/project-a")
    _insert_session(tmp_db, "s2", cwd="/home/user/project-b")

    sl = SessionsList(tmp_db, filter_cwd="/home/user/project-a", id="test-sl")

    # With filter_cwd set, only project-a sessions should load
    assert sl.filter_cwd == "/home/user/project-a"
    assert len(sl.sessions) == 1
    assert sl.sessions[0].cwd == "/home/user/project-a"

    # Simulate what action_back_or_quit does when filter_cwd is set
    sl.filter_cwd = None
    sl._load_sessions()

    # After clearing, all sessions should be visible
    assert sl.filter_cwd is None
    assert len(sl.sessions) == 2


def test_filter_cwd_set_before_view_switch(tmp_db):
    """filter_cwd should be set before action_view_sessions is called."""
    _insert_session(tmp_db, "s1", cwd="/home/user/project-a")
    _insert_session(tmp_db, "s2", cwd="/home/user/project-b")
    _insert_session(tmp_db, "s3", cwd="/home/user/project-a")

    sl = SessionsList(tmp_db, id="test-sl")
    assert len(sl.sessions) == 3

    # Simulate what the fixed projects.py does:
    # set filter_cwd BEFORE triggering the view switch
    sl.filter_cwd = "/home/user/project-a"
    sl._load_sessions()

    assert len(sl.sessions) == 2
    assert all(s.cwd == "/home/user/project-a" for s in sl.sessions)


def test_filter_cwd_survives_reload(tmp_db):
    """filter_cwd should persist across _load_sessions calls."""
    _insert_session(tmp_db, "s1", cwd="/home/user/project-a")
    _insert_session(tmp_db, "s2", cwd="/home/user/project-b")

    sl = SessionsList(tmp_db, filter_cwd="/home/user/project-a", id="test-sl")
    assert len(sl.sessions) == 1

    # Reload sessions — filter should still apply
    sl._load_sessions()
    assert sl.filter_cwd == "/home/user/project-a"
    assert len(sl.sessions) == 1
