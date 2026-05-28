import re
import sqlite3
import time

from seshi.models import Session
from seshi.session_index import STOPWORDS

AGING_THRESHOLD = 1000.0
AGING_FACTOR = 0.9
ARCHIVE_RANK_THRESHOLD = 1.0

_RRF_K = 60
_FUZZY_CACHE: dict[str, str | None] = {}
_FUZZY_CACHE_MAX = 256


# ── Query sanitization (ported from context-mode sanitizeQuery) ──


def _dedupe_tokens(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def sanitize_query(query: str, mode: str = "AND") -> str:
    cleaned = re.sub(r"""['"(){}[\]*:^~]""", " ", query)
    words = _dedupe_tokens(
        [w for w in cleaned.split()
         if w and w.upper() not in ("AND", "OR", "NOT", "NEAR")]
    )
    if not words:
        return '""'
    meaningful = [w for w in words if w.lower() not in STOPWORDS]
    final = meaningful if meaningful else words
    joiner = " OR " if mode == "OR" else " "
    return joiner.join(f'"{w}"' for w in final)


def sanitize_trigram_query(query: str, mode: str = "AND") -> str:
    cleaned = re.sub(r"""["'(){}[\]*:^~]""", "", query).strip()
    if len(cleaned) < 3:
        return ""
    words = _dedupe_tokens([w for w in cleaned.split() if len(w) >= 3])
    if not words:
        return ""
    meaningful = [w for w in words if w.lower() not in STOPWORDS]
    final = meaningful if meaningful else words
    joiner = " OR " if mode == "OR" else " "
    return joiner.join(f'"{w}"' for w in final)


# ── Levenshtein + fuzzy correction (ported from context-mode) ──


def levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        curr = [i]
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                curr.append(prev[j - 1])
            else:
                curr.append(1 + min(prev[j], curr[j - 1], prev[j - 1]))
        prev = curr
    return prev[len(b)]


def max_edit_distance(word_length: int) -> int:
    if word_length <= 4:
        return 1
    if word_length <= 12:
        return 2
    return 3


def fuzzy_correct(conn: sqlite3.Connection, word: str) -> str | None:
    word = word.lower().strip()
    if len(word) < 3:
        return None

    if word in _FUZZY_CACHE:
        result = _FUZZY_CACHE.pop(word)
        _FUZZY_CACHE[word] = result
        return result

    max_dist = max_edit_distance(len(word))
    try:
        candidates = conn.execute(
            "SELECT word FROM vocabulary WHERE length(word) BETWEEN ? AND ?",
            (len(word) - max_dist, len(word) + max_dist),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    best_word: str | None = None
    best_dist = max_dist + 1
    exact_match = False

    for row in candidates:
        candidate = row["word"]
        if candidate == word:
            exact_match = True
            break
        dist = levenshtein(word, candidate)
        if dist < best_dist:
            best_dist = dist
            best_word = candidate

    result = None if exact_match else (best_word if best_dist <= max_dist else None)

    if len(_FUZZY_CACHE) >= _FUZZY_CACHE_MAX:
        oldest = next(iter(_FUZZY_CACHE))
        del _FUZZY_CACHE[oldest]
    _FUZZY_CACHE[word] = result

    return result


# ── Proximity helpers (ported from context-mode) ──


def find_all_positions(text: str, term: str) -> list[int]:
    positions: list[int] = []
    idx = text.find(term)
    while idx != -1:
        positions.append(idx)
        idx = text.find(term, idx + 1)
    return positions


def find_min_span(position_lists: list[list[int]]) -> float:
    if len(position_lists) == 0:
        return float("inf")
    if len(position_lists) == 1:
        return 0.0

    sorted_lists = [sorted(p) for p in position_lists]
    ptrs = [0] * len(sorted_lists)
    min_span = float("inf")

    while True:
        cur_min = float("inf")
        cur_max = float("-inf")
        min_idx = 0

        for i in range(len(sorted_lists)):
            val = sorted_lists[i][ptrs[i]]
            if val < cur_min:
                cur_min = val
                min_idx = i
            if val > cur_max:
                cur_max = val

        span = cur_max - cur_min
        if span < min_span:
            min_span = span

        ptrs[min_idx] += 1
        if ptrs[min_idx] >= len(sorted_lists[min_idx]):
            break

    return min_span


def count_adjacent_pairs(
    position_lists: list[list[int]],
    terms: list[str],
    gap: int = 30,
) -> int:
    if len(position_lists) < 2 or len(terms) < 2:
        return 0
    total = 0
    pairs = min(len(position_lists), len(terms)) - 1
    for i in range(pairs):
        left = position_lists[i]
        right = position_lists[i + 1]
        left_len = len(terms[i])
        j = 0
        for p in left:
            min_start = p + left_len
            max_start = min_start + gap
            while j < len(right) and right[j] < min_start:
                j += 1
            if j < len(right) and right[j] <= max_start:
                total += 1
                j += 1
    return total


# ── FTS5 search functions ──


def search_sessions_porter(
    conn: sqlite3.Connection, query: str, limit: int = 50
) -> list[tuple[str, int]]:
    sanitized = sanitize_query(query, "OR")
    if sanitized == '""':
        return []
    try:
        rows = conn.execute(
            "SELECT session_id, bm25(session_search, 5.0, 2.0, 1.0, 1.5) AS rank "
            "FROM session_search WHERE session_search MATCH ? "
            "ORDER BY rank LIMIT ?",
            (sanitized, limit),
        ).fetchall()
        return [(r["session_id"], i) for i, r in enumerate(rows)]
    except sqlite3.OperationalError:
        return []


def search_sessions_trigram(
    conn: sqlite3.Connection, query: str, limit: int = 50
) -> list[tuple[str, int]]:
    sanitized = sanitize_trigram_query(query, "OR")
    if not sanitized:
        return []
    try:
        rows = conn.execute(
            "SELECT session_id, bm25(session_search_trigram, 5.0, 2.0, 1.0, 1.5) AS rank "
            "FROM session_search_trigram WHERE session_search_trigram MATCH ? "
            "ORDER BY rank LIMIT ?",
            (sanitized, limit),
        ).fetchall()
        return [(r["session_id"], i) for i, r in enumerate(rows)]
    except sqlite3.OperationalError:
        return []


def search_transcripts_ranked(
    conn: sqlite3.Connection, query: str, limit: int = 50
) -> list[tuple[str, int]]:
    if not query or len(query.strip()) < 2:
        return []
    terms = []
    for word in re.split(r"[\s\-]+", query):
        cleaned = "".join(c for c in word if c.isalnum() or c == "_")
        if cleaned:
            terms.append(cleaned)
    if not terms:
        return []
    quoted = [f'"{t}"' for t in terms[:-1]]
    quoted.append(f'"{terms[-1]}"*')
    fts_query = " ".join(quoted)
    try:
        rows = conn.execute(
            "SELECT session_id, rank FROM transcript_fts "
            "WHERE transcript_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_query, limit),
        ).fetchall()
        return [(r["session_id"], i) for i, r in enumerate(rows)]
    except sqlite3.OperationalError:
        return []


# ── RRF merge (ported from context-mode) ──


def rrf_merge(
    result_lists: list[list[tuple[str, int]]], k: int = _RRF_K
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranked_list in result_lists:
        for session_id, rank_pos in ranked_list:
            scores[session_id] = scores.get(session_id, 0.0) + 1.0 / (k + rank_pos + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ── Proximity reranking (ported from context-mode) ──


def apply_proximity_reranking(
    results: list[tuple[str, float]],
    query: str,
    conn: sqlite3.Connection,
) -> list[tuple[str, float]]:
    all_terms = [w.lower() for w in query.split() if len(w) >= 2]
    filtered = [w for w in all_terms if w not in STOPWORDS]
    terms = filtered if filtered else all_terms
    if not terms:
        return results

    reranked = []
    for session_id, rrf_score in results:
        row = conn.execute(
            "SELECT custom_name, first_prompt, cwd FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            reranked.append((session_id, rrf_score))
            continue

        name = (row["custom_name"] or "").lower()
        title_hits = sum(1 for t in terms if t in name)
        title_boost = 0.6 * (title_hits / len(terms)) if title_hits > 0 else 0.0

        content = f"{name} {(row['first_prompt'] or '').lower()} {(row['cwd'] or '').lower()}"
        proximity_boost = 0.0
        phrase_boost = 0.0

        if len(terms) >= 2:
            positions = [find_all_positions(content, t) for t in terms]
            if not any(len(p) == 0 for p in positions):
                min_span = find_min_span(positions)
                proximity_boost = 1.0 / (1.0 + min_span / max(len(content), 1))
                adjacent_pairs = count_adjacent_pairs(positions, terms)
                phrase_boost = 0.5 * min(1.0, adjacent_pairs / 4.0)

        total_boost = title_boost + proximity_boost + phrase_boost
        reranked.append((session_id, rrf_score * (1.0 + total_boost)))

    reranked.sort(key=lambda x: x[1], reverse=True)
    return reranked


# ── Simple term-matching (replaces fuzzy threshold for TUI) ──


def query_matches_text(query: str, text: str) -> bool:
    terms = [t.lower() for t in query.split() if len(t) >= 2]
    if not terms:
        return False
    text_lower = text.lower()
    return any(term in text_lower for term in terms)


# ── Session resolution (unchanged) ──


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


# ── Frecency (unchanged) ──


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


# ── Frecency blending ──


def blend_search_frecency(
    scored: list[tuple[Session, float, float]],
) -> list[tuple[Session, float]]:
    if not scored:
        return []
    max_frecency = max(f for _, _, f in scored) or 1.0
    return [
        (session, search_score * (1.0 + frec / max_frecency))
        for session, search_score, frec in scored
    ]


# ── Main search pipeline ──


def rank_sessions(
    conn: sqlite3.Connection,
    query: str,
    filter_cwd: str | None = None,
) -> list[tuple[Session, float]]:
    porter = search_sessions_porter(conn, query)
    trigram = search_sessions_trigram(conn, query)
    transcripts = search_transcripts_ranked(conn, query)

    merged = rrf_merge([porter, trigram, transcripts])

    if not merged:
        words = [w.lower() for w in query.split() if len(w) >= 3 and w.lower() not in STOPWORDS]
        original = " ".join(words)
        corrected_words = [fuzzy_correct(conn, w) or w for w in words]
        corrected = " ".join(corrected_words)
        if corrected and corrected != original:
            porter = search_sessions_porter(conn, corrected)
            trigram = search_sessions_trigram(conn, corrected)
            transcripts = search_transcripts_ranked(conn, corrected)
            merged = rrf_merge([porter, trigram, transcripts])

    if not merged:
        return []

    merged = apply_proximity_reranking(merged, query, conn)

    sql = "SELECT * FROM sessions WHERE is_archived = 0"
    params: list = []
    if filter_cwd:
        sql += " AND cwd = ?"
        params.append(filter_cwd)
    rows = conn.execute(sql, params).fetchall()
    session_map = {r["session_id"]: Session.from_row(r) for r in rows}

    now = int(time.time())
    scored = []
    for session_id, search_score in merged:
        session = session_map.get(session_id)
        if session:
            scored.append((session, search_score, frecency_score(session, now)))

    results = blend_search_frecency(scored)
    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ── Session listing (unchanged) ──


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


# ── Frecency aging (unchanged) ──


def age_frecency_ranks(conn: sqlite3.Connection) -> int:
    from seshi.db import get_setting, set_setting

    now_ts = int(time.time())
    last_aged = get_setting(conn, "last_aged_at")
    if last_aged and now_ts - int(last_aged) < 300:
        return 0

    rows = conn.execute(
        "SELECT session_id, frecency_rank FROM sessions WHERE is_archived = 0"
    ).fetchall()
    if not rows:
        return 0

    upper_bound = sum(r["frecency_rank"] for r in rows)
    if upper_bound <= AGING_THRESHOLD:
        return 0

    from seshi.transcript import get_existing_session_ids

    existing_ids = get_existing_session_ids()
    live_ids = [r["session_id"] for r in rows if r["session_id"] in existing_ids]
    stale_ids = [r["session_id"] for r in rows if r["session_id"] not in existing_ids]

    if stale_ids:
        stale_ph = ",".join("?" * len(stale_ids))
        conn.execute(
            f"UPDATE sessions SET frecency_rank = 0.0 WHERE session_id IN ({stale_ph})",
            stale_ids,
        )

    if not live_ids:
        conn.commit()
        set_setting(conn, "last_aged_at", str(now_ts))
        return 0

    total = sum(
        r["frecency_rank"] for r in rows if r["session_id"] in existing_ids
    )
    if total <= AGING_THRESHOLD:
        conn.commit()
        set_setting(conn, "last_aged_at", str(now_ts))
        return 0

    scale = AGING_FACTOR * AGING_THRESHOLD / total
    placeholders = ",".join("?" * len(live_ids))
    conn.execute(
        f"UPDATE sessions SET frecency_rank = frecency_rank * ? "
        f"WHERE session_id IN ({placeholders})",
        [scale] + live_ids,
    )

    result = conn.execute(
        f"""UPDATE sessions SET is_archived = 1
           WHERE is_archived = 0
             AND frecency_rank < ?
             AND is_favorite = 0
             AND custom_name IS NULL
             AND session_id NOT IN (SELECT session_id FROM tags)
             AND session_id IN ({placeholders})""",
        [ARCHIVE_RANK_THRESHOLD] + live_ids,
    )
    archived_count = result.rowcount
    conn.commit()
    set_setting(conn, "last_aged_at", str(now_ts))
    return archived_count
