import math
import sqlite3
import time

from rapidfuzz import fuzz

from seshi.models import Session
from seshi.prompt_text import strip_markup_tags

# Minimum raw fuzzy score (before field weighting) to consider a match
# meaningful.  ``partial_ratio`` returns 20-40 for incidental single-
# character overlaps; 50 filters that noise while keeping real matches.
FUZZY_MIN_SCORE = 50


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

    scored = []
    for row in rows:
        session = Session.from_row(row)
        r1 = fuzzy_match(query, session.custom_name or "")
        r2 = fuzzy_match(query, strip_markup_tags(session.first_prompt or ""))
        r3 = fuzzy_match(query, session.cwd)
        if max(r1, r2, r3) >= FUZZY_MIN_SCORE:
            best = max(r1 * 4, r2 * 2, r3 * 1)
            scored.append((session, best))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def frecency_score(
    session: Session,
    now: int | None = None,
    cwd_counts: dict[str, int] | None = None,
) -> float:
    if now is None:
        now = int(time.time())
    age_hours = (now - session.last_activity_at) / 3600
    recency = 1.0 / (1.0 + age_hours / 24.0)
    count = (cwd_counts or {}).get(session.cwd, 1)
    frequency = math.log(1 + count)
    return recency * 0.7 + frequency * 0.3


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
        cwd_counts: dict[str, int] = {}
        for s in sessions:
            cwd_counts[s.cwd] = cwd_counts.get(s.cwd, 0) + 1
        favorites = [s for s in sessions if s.is_favorite]
        non_favorites = [s for s in sessions if not s.is_favorite]
        favorites.sort(key=lambda s: frecency_score(s, now, cwd_counts), reverse=True)
        non_favorites.sort(key=lambda s: frecency_score(s, now, cwd_counts), reverse=True)
        sessions = favorites + non_favorites
    elif sort_mode == "frequency":
        cwd_counts = {}
        for s in sessions:
            cwd_counts[s.cwd] = cwd_counts.get(s.cwd, 0) + 1
        favorites = [s for s in sessions if s.is_favorite]
        non_favorites = [s for s in sessions if not s.is_favorite]
        non_favorites.sort(key=lambda s: (-cwd_counts.get(s.cwd, 0), -s.last_activity_at))
        sessions = favorites + non_favorites

    if limit:
        sessions = sessions[:limit]

    return sessions
