import logging
import sqlite3
import time

from seshi.paths import CLAUDE_PROJECTS, UUID_RE, resolve_best_cwd
from seshi.transcript import find_transcript_path, parse_transcript

log = logging.getLogger(__name__)

# Bump when parse_transcript() or strip_system_blocks() changes in a way
# that affects first_prompt extraction (triggers fix_prompts re-run).
# v1 = PR #82 (skip isMeta)  v2 = PR #89 (strip_system_blocks)
# v3 = strip bash-input/stdout/stderr + local-command-stderr
# v4 = extract ai_title from transcript
# v5 = extract slash-command text instead of stripping it (#124)
PROMPT_FIX_VERSION = 5


def scan_projects(
    conn: sqlite3.Connection,
    projects_root=None,
    verbose: bool = False,
) -> int:
    root = projects_root or CLAUDE_PROJECTS
    if not root.is_dir():
        return 0

    count = 0

    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue

        cwd = resolve_best_cwd(project_dir.name)
        if verbose:
            print(f"scanning {project_dir.name} → {cwd}")

        for entry in project_dir.iterdir():
            if entry.name == "skill-injections.jsonl":
                continue

            if entry.is_file() and entry.suffix == ".jsonl":
                session_id = entry.stem
                if not UUID_RE.match(session_id):
                    continue

                summary = parse_transcript(entry)
                mtime = int(entry.stat().st_mtime)
                created = summary.first_ts or mtime
                last_activity = summary.last_ts or mtime

                result = conn.execute(
                    """INSERT OR IGNORE INTO sessions
                    (session_id, cwd, launch_argv_json, first_prompt,
                     ai_title, message_count, token_count, is_backfilled,
                     created_at, last_activity_at, status)
                    VALUES (?, ?, '[]', ?, ?, ?, ?, 1, ?, ?, 'done')""",
                    (
                        session_id, cwd, summary.first_prompt,
                        summary.ai_title,
                        summary.message_count, summary.token_count,
                        created, last_activity,
                    ),
                )
                if result.rowcount > 0:
                    count += 1
                    if verbose:
                        print(f"  + {session_id[:8]} ({summary.message_count} msgs)")
                else:
                    updates = []
                    params = []
                    if summary.first_prompt:
                        updates.append("first_prompt = CASE WHEN first_prompt IS NULL OR first_prompt != ? THEN ? ELSE first_prompt END")
                        params.extend([summary.first_prompt, summary.first_prompt])
                    if summary.ai_title:
                        updates.append("ai_title = ?")
                        params.append(summary.ai_title)
                    if updates:
                        params.append(session_id)
                        conn.execute(
                            f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
                            params,
                        )

            elif entry.is_dir() and UUID_RE.match(entry.name):
                session_id = entry.name
                existing = conn.execute(
                    "SELECT 1 FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if existing:
                    continue

                jsonl_file = project_dir / f"{session_id}.jsonl"
                if jsonl_file.exists():
                    continue

                dir_mtime = int(entry.stat().st_mtime)
                result = conn.execute(
                    """INSERT OR IGNORE INTO sessions
                    (session_id, cwd, launch_argv_json, is_backfilled,
                     created_at, last_activity_at)
                    VALUES (?, ?, '[]', 1, ?, ?)""",
                    (session_id, cwd, dir_mtime, dir_mtime),
                )
                if result.rowcount > 0:
                    count += 1
                    if verbose:
                        print(f"  + {session_id[:8]} (dir only)")

    conn.commit()

    from seshi.transcript_index import index_pending
    try:
        index_pending(conn)
    except Exception:
        log.debug("FTS indexing failed", exc_info=True)

    from seshi.prompt_index import index_pending_prompts
    try:
        index_pending_prompts(conn)
    except Exception:
        log.debug("prompt indexing failed", exc_info=True)

    from seshi.session_index import index_pending_search
    try:
        index_pending_search(conn)
    except Exception:
        log.debug("session search indexing failed", exc_info=True)

    return count


def fix_prompts(
    conn: sqlite3.Connection,
    verbose: bool = False,
) -> int:
    rows = conn.execute("SELECT session_id, first_prompt, ai_title FROM sessions").fetchall()
    count = 0
    for row in rows:
        session_id = row["session_id"]
        path = find_transcript_path(session_id)
        if not path:
            continue
        summary = parse_transcript(path)
        changed = False
        if summary.first_prompt != row["first_prompt"]:
            conn.execute(
                "UPDATE sessions SET first_prompt = ? WHERE session_id = ?",
                (summary.first_prompt, session_id),
            )
            changed = True
        if summary.ai_title and summary.ai_title != row["ai_title"]:
            conn.execute(
                "UPDATE sessions SET ai_title = ? WHERE session_id = ?",
                (summary.ai_title, session_id),
            )
            changed = True
        if changed:
            count += 1
            if verbose:
                label = (summary.first_prompt or "(untitled)")[:60]
                print(f"  ~ {session_id[:8]}: {label}")
    conn.commit()
    return count


def auto_scan(conn: sqlite3.Connection, interval: int = 120) -> None:
    from seshi.db import get_setting, set_setting

    now_ts = int(time.time())
    last_scan = get_setting(conn, "last_scan_at")
    if last_scan and now_ts - int(last_scan) < interval:
        return

    scan_projects(conn)
    set_setting(conn, "last_scan_at", str(now_ts))

    stored = get_setting(conn, "prompts_fixed")
    if not stored or int(stored) < PROMPT_FIX_VERSION:
        fix_prompts(conn)
        set_setting(conn, "prompts_fixed", str(PROMPT_FIX_VERSION))
