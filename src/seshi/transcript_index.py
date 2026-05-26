import json
import sqlite3
from pathlib import Path

from seshi.transcript import find_transcript_path


def extract_full_text(path: Path) -> str:
    parts: list[str] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text.strip():
                                parts.append(text)
    except OSError:
        pass
    return "\n".join(parts)


def index_session(conn: sqlite3.Connection, session_id: str) -> bool:
    path = find_transcript_path(session_id)
    if not path:
        return False

    try:
        file_size = path.stat().st_size
    except OSError:
        return False

    row = conn.execute(
        "SELECT file_size FROM transcript_index_meta WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row and row["file_size"] == file_size:
        return False

    text = extract_full_text(path)
    if not text.strip():
        return False

    conn.execute(
        "DELETE FROM transcript_fts WHERE session_id = ?", (session_id,)
    )
    conn.execute(
        "INSERT INTO transcript_fts (session_id, content) VALUES (?, ?)",
        (session_id, text),
    )
    conn.execute(
        "INSERT OR REPLACE INTO transcript_index_meta (session_id, file_size) VALUES (?, ?)",
        (session_id, file_size),
    )
    return True


def index_pending(conn: sqlite3.Connection) -> int:
    try:
        conn.execute("SELECT 1 FROM transcript_fts LIMIT 0")
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
        if index_session(conn, session_id):
            count += 1
    if count:
        conn.commit()
    return count


def search_transcripts(conn: sqlite3.Connection, query: str) -> dict[str, float]:
    if not query or len(query.strip()) < 2:
        return {}

    import re
    terms = []
    for word in re.split(r'[\s\-]+', query):
        cleaned = "".join(c for c in word if c.isalnum() or c == "_")
        if cleaned:
            terms.append(cleaned)
    if not terms:
        return {}

    quoted = [f'"{t}"' for t in terms[:-1]]
    quoted.append(f'"{terms[-1]}"*')
    fts_query = " ".join(quoted)

    try:
        rows = conn.execute(
            "SELECT session_id, rank FROM transcript_fts WHERE transcript_fts MATCH ?",
            (fts_query,),
        ).fetchall()
        if not rows:
            return {}
        scores = {r["session_id"]: r["rank"] for r in rows}
        best = min(scores.values())
        worst = max(scores.values())
        if worst == best:
            return {sid: 80.0 for sid in scores}
        spread = worst - best
        return {
            sid: 55.0 + 45.0 * (worst - raw) / spread
            for sid, raw in scores.items()
        }
    except sqlite3.OperationalError:
        return {}
