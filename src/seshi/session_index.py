import re
import sqlite3

from seshi.prompt_text import strip_markup_tags, strip_system_blocks

STOPWORDS = frozenset([
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "has", "his", "how", "its", "may",
    "new", "now", "old", "see", "way", "who", "did", "get", "got", "let",
    "say", "she", "too", "use", "will", "with", "this", "that", "from",
    "they", "been", "have", "many", "some", "them", "than", "each", "make",
    "like", "just", "over", "such", "take", "into", "year", "your", "good",
    "could", "would", "about", "which", "their", "there", "other", "after",
    "should", "through", "also", "more", "most", "only", "very", "when",
    "what", "then", "these", "those", "being", "does", "done", "both",
    "same", "still", "while", "where", "here", "were", "much",
    "update", "updates", "updated", "deps", "dev", "tests", "test",
    "add", "added", "fix", "fixed", "run", "running", "using",
])

_WORD_SPLIT_RE = re.compile(r"[^\w]+", re.UNICODE)


def extract_vocabulary(conn: sqlite3.Connection, text: str) -> int:
    words = _WORD_SPLIT_RE.split(text.lower())
    unique = {w for w in words if len(w) >= 3 and w not in STOPWORDS}
    if not unique:
        return 0
    inserted = 0
    for word in unique:
        result = conn.execute(
            "INSERT OR IGNORE INTO vocabulary (word) VALUES (?)", (word,)
        )
        inserted += result.rowcount
    return inserted


def index_session_search(conn: sqlite3.Connection, session_id: str) -> bool:
    row = conn.execute(
        "SELECT custom_name, first_prompt, cwd FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return False

    name = row["custom_name"] or ""
    first_prompt = strip_markup_tags(strip_system_blocks(row["first_prompt"] or ""))
    cwd = row["cwd"] or ""

    prompt_rows = conn.execute(
        "SELECT text FROM prompts WHERE session_id = ? ORDER BY prompt_index",
        (session_id,),
    ).fetchall()
    prompt_text = "\n".join(strip_system_blocks(r["text"]) for r in prompt_rows)

    conn.execute("DELETE FROM session_search WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM session_search_trigram WHERE session_id = ?", (session_id,))

    conn.execute(
        "INSERT INTO session_search (session_id, name, first_prompt, cwd, prompt_text) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, name, first_prompt, cwd, prompt_text),
    )
    conn.execute(
        "INSERT INTO session_search_trigram (session_id, name, first_prompt, cwd, prompt_text) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, name, first_prompt, cwd, prompt_text),
    )

    all_text = f"{name} {first_prompt} {cwd} {prompt_text}"
    extract_vocabulary(conn, all_text)

    return True


def index_pending_search(conn: sqlite3.Connection) -> int:
    try:
        conn.execute("SELECT 1 FROM session_search LIMIT 0")
    except sqlite3.OperationalError:
        return 0

    rows = conn.execute(
        "SELECT session_id FROM sessions WHERE is_archived = 0"
    ).fetchall()
    all_ids = [r["session_id"] for r in rows]
    if not all_ids:
        return 0

    placeholders = ",".join("?" * len(all_ids))
    already = conn.execute(
        f"SELECT DISTINCT session_id FROM session_search WHERE session_id IN ({placeholders})",
        all_ids,
    ).fetchall()
    already_set = {r["session_id"] for r in already}

    prompt_counts: dict[str, int] = {}
    for row in conn.execute(
        f"SELECT session_id, COUNT(*) as cnt FROM prompts "
        f"WHERE session_id IN ({placeholders}) GROUP BY session_id",
        all_ids,
    ).fetchall():
        prompt_counts[row["session_id"]] = row["cnt"]

    indexed_prompt_lengths: dict[str, int] = {}
    for sid in already_set:
        row = conn.execute(
            "SELECT length(prompt_text) as len FROM session_search WHERE session_id = ?",
            (sid,),
        ).fetchone()
        indexed_prompt_lengths[sid] = row["len"] if row and row["len"] else 0

    count = 0
    for session_id in all_ids:
        if session_id not in already_set:
            if index_session_search(conn, session_id):
                count += 1
        elif prompt_counts.get(session_id, 0) > 0 and indexed_prompt_lengths.get(session_id, 0) == 0:
            if index_session_search(conn, session_id):
                count += 1
    if count:
        conn.commit()
    return count


def reindex_session(conn: sqlite3.Connection, session_id: str) -> bool:
    result = index_session_search(conn, session_id)
    if result:
        conn.commit()
    return result
