import sqlite3

from seshi.transcript import find_transcript_path, extract_user_prompts


def index_session_prompts(conn: sqlite3.Connection, session_id: str) -> bool:
    path = find_transcript_path(session_id)
    if not path:
        return False

    try:
        file_size = path.stat().st_size
    except OSError:
        return False

    row = conn.execute(
        "SELECT file_size FROM prompt_index_meta WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row and row["file_size"] == file_size:
        return False

    prompts = extract_user_prompts(path)

    conn.execute("DELETE FROM prompts WHERE session_id = ?", (session_id,))
    for i, msg in enumerate(prompts):
        ts_epoch = None
        if msg.timestamp:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(msg.timestamp.replace("Z", "+00:00"))
                ts_epoch = int(dt.timestamp())
            except (ValueError, OSError):
                pass
        conn.execute(
            "INSERT INTO prompts (session_id, prompt_index, text, timestamp_epoch) VALUES (?, ?, ?, ?)",
            (session_id, i, msg.text, ts_epoch),
        )

    conn.execute(
        "INSERT OR REPLACE INTO prompt_index_meta (session_id, file_size) VALUES (?, ?)",
        (session_id, file_size),
    )
    return True


def index_pending_prompts(conn: sqlite3.Connection) -> int:
    try:
        conn.execute("SELECT 1 FROM prompts LIMIT 0")
    except sqlite3.OperationalError:
        return 0

    rows = conn.execute(
        "SELECT session_id FROM sessions WHERE is_archived = 0"
    ).fetchall()
    all_ids = [r["session_id"] for r in rows]
    if not all_ids:
        return 0

    count = 0
    for session_id in all_ids:
        if index_session_prompts(conn, session_id):
            count += 1
    if count:
        conn.commit()
    return count
