import sqlite3
import time

from rapidfuzz import fuzz

from seshi.models import Session
from seshi.prompt_text import strip_markup_tags

FUZZY_THRESHOLD = 55
AGING_THRESHOLD = 1000.0
AGING_FACTOR = 0.9
ARCHIVE_RANK_THRESHOLD = 1.0


def fuzzy_match(query: str, string: str) -> int:
    if not query or not string:
        return 0
    return int(fuzz.partial_ratio(query, string, processor=str.lower))


def session_resolve(conn: sqlite3.Connection, identifier: str) -> Session | None:
    row = conn.execute(
        "SELECT * FROM sessions WHERE custom_name = ? COLLATE NOCASE ORDER BY last_activity_at DESC LIMIT 1",
        (identifier,),
    ).fetchone()
    if row:
        return Session.from_row(row)

    row = conn.execute(
        "SELECT * FROM sessions WHERE session_id = ?",
        (identifier,),
    ).fetchone()
    if row:
        return Session.from_row(row)

    return None


def _recency_multiplier(age_hours: float) -> float:
    if age_hours < 4:
        return 4.0
    if age_hours < 24:
        return 2.0
    if age_hours < 24 * 7:
        return 1.0
    if age_hours < 24 * 28:
        return 0.5
    return 0.25


def frecency_score(
    session: Session,
    now: int | None = None,
) -> float:
    if now is None:
        now = int(time.time())
    age_hours = (now - session.last_activity_at) / 3600
    return session.frecency_rank * _recency_multiplier(age_hours)


def rank_sessions(
    conn: sqlite3.Connection,
    query: str,
    filter_cwd: str | None = None,
) -> list[tuple[Session, int]]:
    sql = "SELECT * FROM sessions WHERE is_archived = 0"
    params: list = []
    if filter_cwd:
        sql += " AND cwd = ?"
        params.append(filter_cwd)
    sql += " ORDER BY is_favorite DESC, last_activity_at DESC"
    rows = conn.execute(sql, params).fetchall()

    now = int(time.time())
    scored = []
    for row in rows:
        session = Session.from_row(row)
        r1 = fuzzy_match(query, session.custom_name or "")
        r2 = fuzzy_match(query, strip_markup_tags(session.first_prompt or ""))
        r3 = fuzzy_match(query, session.cwd)
        if max(r1, r2, r3) >= FUZZY_THRESHOLD:
            fuzzy = max(r1 * 4, r2 * 2, r3)
            frec = frecency_score(session, now)
            scored.append((session, fuzzy, frec))

    if not scored:
        return []

    max_frecency = max(f for _, _, f in scored) or 1.0
    results = []
    for session, fuzzy, frec in scored:
        blended = fuzzy * (1.0 + frec / max_frecency)
        results.append((session, int(blended)))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def list_sessions(
    conn: sqlite3.Connection,
    filter_cwd: str | None = None,
    tags: list[str] | None = None,
    include_archived: bool = False,
    sort_mode: str = "frecency",
    limit: int | None = None,
) -> list[Session]:
    if include_archived:
        sql = "SELECT * FROM sessions WHERE 1=1"
    else:
        sql = "SELECT * FROM sessions WHERE is_archived = 0"
    params: list = []

    if filter_cwd:
        sql += " AND cwd = ?"
        params.append(filter_cwd)

    if tags:
        for tag in tags:
            sql += " AND session_id IN (SELECT session_id FROM tags WHERE tag = ?)"
            params.append(tag)

    sql += " ORDER BY is_favorite DESC, last_activity_at DESC"
    rows = conn.execute(sql, params).fetchall()
    sessions = [Session.from_row(r) for r in rows]

    if sort_mode == "frecency":
        now = int(time.time())
        favorites = [s for s in sessions if s.is_favorite]
        non_favorites = [s for s in sessions if not s.is_favorite]
        favorites.sort(key=lambda s: frecency_score(s, now), reverse=True)
        non_favorites.sort(key=lambda s: frecency_score(s, now), reverse=True)
        sessions = favorites + non_favorites
    elif sort_mode == "frequency":
        favorites = [s for s in sessions if s.is_favorite]
        non_favorites = [s for s in sessions if not s.is_favorite]
        non_favorites.sort(key=lambda s: (-s.resume_count, -s.last_activity_at))
        sessions = favorites + non_favorites

    if limit:
        sessions = sessions[:limit]

    return sessions


def age_frecency_ranks(conn: sqlite3.Connection) -> int:
    from seshi.transcript import get_existing_session_ids

    rows = conn.execute(
        "SELECT session_id, frecency_rank FROM sessions WHERE is_archived = 0"
    ).fetchall()
    if not rows:
        return 0

    existing_ids = get_existing_session_ids()
    live_ids = [r["session_id"] for r in rows if r["session_id"] in existing_ids]
    if not live_ids:
        return 0

    total = sum(
        r["frecency_rank"] for r in rows if r["session_id"] in existing_ids
    )
    if total <= AGING_THRESHOLD:
        return 0

    scale = AGING_FACTOR * AGING_THRESHOLD / total
    placeholders = ",".join("?" * len(live_ids))
    conn.execute(
        f"UPDATE sessions SET frecency_rank = frecency_rank * ? "
        f"WHERE session_id IN ({placeholders})",
        [scale] + live_ids,
    )

    result = conn.execute(
        """UPDATE sessions SET is_archived = 1
           WHERE is_archived = 0
             AND frecency_rank < ?
             AND is_favorite = 0
             AND custom_name IS NULL
             AND session_id NOT IN (SELECT session_id FROM tags)""",
        (ARCHIVE_RANK_THRESHOLD,),
    )
    archived_count = result.rowcount
    conn.commit()
    return archived_count
