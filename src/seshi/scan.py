import logging
import sqlite3

from seshi.paths import CLAUDE_PROJECTS, UUID_RE, resolve_best_cwd
from seshi.transcript import parse_transcript

log = logging.getLogger(__name__)


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
                     message_count, token_count, is_backfilled,
                     created_at, last_activity_at, status)
                    VALUES (?, ?, '[]', ?, ?, ?, 1, ?, ?, 'done')""",
                    (
                        session_id, cwd, summary.first_prompt,
                        summary.message_count, summary.token_count,
                        created, last_activity,
                    ),
                )
                if result.rowcount > 0:
                    count += 1
                    if verbose:
                        print(f"  + {session_id[:8]} ({summary.message_count} msgs)")

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

    return count
