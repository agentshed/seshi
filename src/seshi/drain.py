import json
import os
import sqlite3
import time

from seshi.paths import QUEUE_PATH


def drain_queue(conn: sqlite3.Connection) -> int:
    if not QUEUE_PATH.exists():
        return 0

    try:
        text = QUEUE_PATH.read_text()
    except OSError:
        return 0

    if not text.strip():
        return 0

    lines = text.splitlines()
    count = 0

    with conn:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("event")
            session_id = event.get("session_id")
            if not session_id:
                continue

            ts = event.get("ts", int(time.time()))

            if event_type == "start":
                argv_json = event.get("argv", "[]")
                if isinstance(argv_json, str):
                    pass
                else:
                    argv_json = json.dumps(argv_json)

                env = event.get("env", {})
                env_json = json.dumps(env) if env else None

                cwd = event.get("cwd", "")
                if cwd:
                    cwd = os.path.normpath(cwd)

                conn.execute(
                    """INSERT OR IGNORE INTO sessions
                    (session_id, cwd, launch_argv_json, env_json,
                     git_branch, git_sha, first_prompt,
                     created_at, last_activity_at, origin_host)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        cwd,
                        argv_json,
                        env_json,
                        event.get("git_branch") or None,
                        event.get("git_sha") or None,
                        event.get("first_prompt") or None,
                        ts,
                        ts,
                        event.get("origin_host") or None,
                    ),
                )
                count += 1

            elif event_type == "stop":
                first_prompt = event.get("first_prompt") or None
                conn.execute(
                    """UPDATE sessions SET
                        message_count = ?,
                        token_count = ?,
                        last_activity_at = ?,
                        status = 'done',
                        first_prompt = COALESCE(first_prompt, ?)
                    WHERE session_id = ?""",
                    (
                        event.get("message_count", 0),
                        event.get("token_count", 0),
                        ts,
                        first_prompt,
                        session_id,
                    ),
                )
                count += 1

    try:
        QUEUE_PATH.write_text("")
    except OSError:
        pass

    return count
