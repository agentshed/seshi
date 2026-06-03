from __future__ import annotations

import json
import re
import sqlite3

from seshi.models import Session

SAFE_CHARS_RE = re.compile(r"^[A-Za-z0-9_./@:=-]+$")


def shell_quote(s: str) -> str:
    if not s:
        return "''"
    if SAFE_CHARS_RE.match(s):
        return s
    return "'" + s.replace("'", "'\\''") + "'"


def build_resume_line(
    session: Session, conn: sqlite3.Connection | None = None
) -> str:
    try:
        argv = json.loads(session.launch_argv_json)
    except (json.JSONDecodeError, TypeError):
        argv = []

    if isinstance(argv, str):
        argv = argv.split()

    if not isinstance(argv, list):
        argv = []

    filtered = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg == "--resume":
            skip_next = True
            continue
        if arg.startswith("--resume="):
            continue
        filtered.append(arg)

    if not filtered or filtered[0] != "claude":
        filtered.insert(0, "claude")

    # Inject persistent Claude CLI flags before --resume
    if conn is not None:
        from seshi.claude_flags import build_args

        extra = build_args(conn)
        if extra:
            filtered.extend(extra)

    filtered.extend(["--resume", session.session_id])

    quoted_args = " ".join(shell_quote(a) for a in filtered)
    quoted_cwd = shell_quote(session.cwd)

    return f"cd {quoted_cwd} && exec {quoted_args}\n"
