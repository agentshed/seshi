"""Shared test helpers for TUI tests."""
import sqlite3

from seshi.db import init_schema, set_setting
from seshi.live import LiveInfo
from seshi.models import Session


def make_session(sid="a0b1c2d3-0000-0000-0000-000000000000", cwd="/tmp/proj",
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


def make_live(sid="a0b1c2d3-0000-0000-0000-000000000000", status="busy",
              kind="background", detail=None, cwd="/tmp/proj", name=None):
    return LiveInfo(
        session_id=sid, pid=123, kind=kind, status=status,
        detail=detail, name=name, daemon_short=sid[:8], cwd=cwd,
    )


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    set_setting(conn, "hide_stale_sessions", "0")
    return conn


def insert_session(conn, session):
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
