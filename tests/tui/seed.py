from __future__ import annotations

import sqlite3
import os
import time
import uuid
from typing import Sequence

from seshi.db import init_schema


def make_session_id() -> str:
    return str(uuid.uuid4())


def seed_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


def insert_session(
    conn: sqlite3.Connection,
    *,
    session_id: str | None = None,
    cwd: str = "/tmp/test-project",
    launch_argv_json: str = '["claude"]',
    env_json: str | None = None,
    git_branch: str | None = None,
    git_sha: str | None = None,
    first_prompt: str | None = None,
    custom_name: str | None = None,
    is_favorite: int = 0,
    is_archived: int = 0,
    is_backfilled: int = 0,
    message_count: int = 5,
    token_count: int = 1000,
    status: str | None = "completed",
    created_at: int | None = None,
    last_activity_at: int | None = None,
    origin_host: str | None = None,
    schema_version: int = 1,
    tags: Sequence[str] = (),
) -> str:
    sid = session_id or make_session_id()
    now = int(time.time())
    cat = created_at or now
    lat = last_activity_at or now

    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, env_json, git_branch, git_sha,
         first_prompt, custom_name, is_favorite, is_archived, is_backfilled,
         message_count, token_count, status, created_at, last_activity_at,
         origin_host, schema_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, cwd, launch_argv_json, env_json, git_branch, git_sha,
         first_prompt, custom_name, is_favorite, is_archived, is_backfilled,
         message_count, token_count, status, cat, lat,
         origin_host, schema_version),
    )

    for tag in tags:
        conn.execute(
            "INSERT INTO tags (session_id, tag) VALUES (?, ?)",
            (sid, tag),
        )

    conn.commit()
    return sid


def seed_time_spread(conn: sqlite3.Connection, count: int = 20) -> list[str]:
    now = int(time.time())
    ids = []
    buckets = [
        ("today", 0),
        ("today", 2 * 3600),
        ("today", 6 * 3600),
        ("yesterday", 30 * 3600),
        ("yesterday", 40 * 3600),
        ("this_week", 3 * 86400),
        ("this_week", 5 * 86400),
        ("this_month", 10 * 86400),
        ("this_month", 20 * 86400),
        ("older", 60 * 86400),
    ]

    for i in range(count):
        bucket_name, offset = buckets[i % len(buckets)]
        ts = now - offset - (i * 60)
        sid = insert_session(
            conn,
            cwd=f"/tmp/project-{i % 5}",
            first_prompt=f"Session {i} prompt ({bucket_name})",
            custom_name=f"session-{i}" if i % 3 == 0 else None,
            created_at=ts,
            last_activity_at=ts,
        )
        ids.append(sid)

    return ids


def seed_for_search(conn: sqlite3.Connection) -> dict[str, str]:
    now = int(time.time())
    sessions = {}

    sessions["auth"] = insert_session(
        conn,
        custom_name="auth-rewrite",
        first_prompt="Rewrite the OAuth2 authentication flow",
        cwd="/tmp/auth-project",
        last_activity_at=now - 3600,
    )
    sessions["bug_fix"] = insert_session(
        conn,
        custom_name="fix-login-bug",
        first_prompt="Fix the login page crash on Safari",
        cwd="/tmp/web-app",
        last_activity_at=now - 7200,
    )
    sessions["tagged"] = insert_session(
        conn,
        custom_name="tagged-session",
        first_prompt="Add unit tests for the API",
        cwd="/tmp/api-project",
        tags=["sprint42", "testing"],
        last_activity_at=now - 1800,
    )
    sessions["unrelated"] = insert_session(
        conn,
        first_prompt="Update README",
        cwd="/tmp/docs",
        last_activity_at=now - 10800,
    )

    return sessions


def seed_for_actions(conn: sqlite3.Connection) -> dict[str, str]:
    now = int(time.time())
    sessions = {}

    sessions["to_rename"] = insert_session(
        conn,
        custom_name="old-name",
        first_prompt="Help me refactor",
        cwd="/tmp/refactor",
        last_activity_at=now,
    )
    sessions["to_tag"] = insert_session(
        conn,
        first_prompt="Add caching layer",
        cwd="/tmp/cache",
        last_activity_at=now - 600,
    )
    sessions["to_favorite"] = insert_session(
        conn,
        custom_name="fav-candidate",
        first_prompt="Important session",
        cwd="/tmp/important",
        last_activity_at=now - 1200,
    )
    sessions["to_archive"] = insert_session(
        conn,
        custom_name="archive-me",
        first_prompt="Old session",
        cwd="/tmp/old",
        last_activity_at=now - 1800,
    )
    sessions["to_delete"] = insert_session(
        conn,
        custom_name="delete-me",
        first_prompt="Throwaway session",
        cwd="/tmp/throwaway",
        tags=["deleteme"],
        last_activity_at=now - 2400,
    )

    return sessions


def seed_for_bulk(conn: sqlite3.Connection, count: int = 10) -> list[str]:
    now = int(time.time())
    ids = []
    for i in range(count):
        sid = insert_session(
            conn,
            custom_name=f"bulk-{i}",
            first_prompt=f"Bulk session {i}",
            cwd="/tmp/bulk-project",
            last_activity_at=now - (i * 600),
        )
        ids.append(sid)
    return ids


def seed_unicode(conn: sqlite3.Connection) -> dict[str, str]:
    now = int(time.time())
    sessions = {}

    sessions["cjk"] = insert_session(
        conn,
        custom_name="修正バグ",
        first_prompt="Fix the Unicode rendering issue",
        cwd="/tmp/unicode-test",
        last_activity_at=now,
    )
    sessions["emoji"] = insert_session(
        conn,
        custom_name="Bug Fix \U0001f41b\U0001f389",
        first_prompt="Fix all the bugs",
        cwd="/tmp/emoji-test",
        last_activity_at=now - 600,
    )
    sessions["rtl"] = insert_session(
        conn,
        custom_name="مرحبا",
        first_prompt="Arabic text test",
        cwd="/tmp/rtl-test",
        last_activity_at=now - 1200,
    )

    return sessions


def seed_for_projects(conn: sqlite3.Connection) -> dict[str, list[str]]:
    now = int(time.time())
    projects: dict[str, list[str]] = {}

    cwds = [
        ("/tmp/project-alpha", 8),
        ("/tmp/project-beta", 3),
        ("/tmp/project-gamma", 1),
    ]

    for cwd, count in cwds:
        ids = []
        for i in range(count):
            sid = insert_session(
                conn,
                cwd=cwd,
                first_prompt=f"Work on {cwd} #{i}",
                last_activity_at=now - (i * 3600),
            )
            ids.append(sid)
        projects[cwd] = ids

    return projects
