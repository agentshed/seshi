import time
from seshi.search import fuzzy_match, session_resolve, rank_sessions, frecency_score, list_sessions, FUZZY_MIN_SCORE
from seshi.models import Session


def _insert_session(conn, session_id, cwd="/home", custom_name=None, first_prompt=None, is_favorite=0, ts=None):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, custom_name, first_prompt,
         is_favorite, created_at, last_activity_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (session_id, cwd, "[]", custom_name, first_prompt, is_favorite, ts, ts),
    )
    conn.commit()


def test_fuzzy_match_exact():
    assert fuzzy_match("abc", "abc") > 0


def test_fuzzy_match_no_match():
    assert fuzzy_match("xyz", "abc") == 0


def test_fuzzy_match_case_insensitive():
    assert fuzzy_match("ABC", "abc") > 0


def test_fuzzy_match_empty_query():
    assert fuzzy_match("", "abc") == 0


def test_fuzzy_match_substring_quality():
    score_exact = fuzzy_match("auth", "auth-rewrite")
    score_partial = fuzzy_match("auth", "a]u[t}h{")
    assert score_exact > score_partial


def test_session_resolve_by_name(tmp_db):
    _insert_session(tmp_db, "id-1", custom_name="my-session")
    result = session_resolve(tmp_db, "my-session")
    assert result is not None
    assert result.session_id == "id-1"


def test_session_resolve_by_id(tmp_db):
    _insert_session(tmp_db, "id-1")
    result = session_resolve(tmp_db, "id-1")
    assert result is not None


def test_session_resolve_not_found(tmp_db):
    result = session_resolve(tmp_db, "nonexistent")
    assert result is None


def test_rank_sessions(tmp_db):
    _insert_session(tmp_db, "id-1", custom_name="auth-rewrite")
    _insert_session(tmp_db, "id-2", first_prompt="fix auth bug")
    _insert_session(tmp_db, "id-3", first_prompt="unrelated work")
    results = rank_sessions(tmp_db, "auth")
    assert len(results) >= 2
    assert results[0][0].session_id in ("id-1", "id-2")


def test_rank_sessions_strips_markup_tags_from_prompt(tmp_db):
    _insert_session(
        tmp_db,
        "id-1",
        first_prompt=(
            "<local-command-caveat>local-command caveat</local-command-caveat> Open the repo"
        ),
    )
    _insert_session(tmp_db, "id-2", first_prompt="local command checklist")

    results = rank_sessions(tmp_db, "local-command")

    # Both should match; verify markup tags are stripped so id-1 matches
    result_ids = [session.session_id for session, _ in results]
    assert "id-1" in result_ids
    assert "id-2" in result_ids
    assert len(results) == 2


def test_rank_sessions_filters_low_quality_matches(tmp_db):
    """Sessions with only incidental character overlap should be excluded."""
    _insert_session(tmp_db, "id-match", custom_name="OAuth migration")
    _insert_session(tmp_db, "id-noise1", first_prompt="fix the build pipeline")
    _insert_session(tmp_db, "id-noise2", custom_name="refactor utils")
    _insert_session(tmp_db, "id-noise3", first_prompt="add tests for parser")

    results = rank_sessions(tmp_db, "OAuth")
    session_ids = [s.session_id for s, _ in results]

    # Only the session with a real match should appear
    assert "id-match" in session_ids
    # Noise sessions that only share a single common letter should be filtered
    assert len(results) <= 2, (
        f"Expected at most 2 results for 'OAuth', got {len(results)}: {session_ids}"
    )


def test_rank_sessions_no_results_for_gibberish(tmp_db):
    """A query with no meaningful match should return zero results."""
    _insert_session(tmp_db, "id-1", custom_name="auth-rewrite")
    _insert_session(tmp_db, "id-2", first_prompt="fix auth bug")

    results = rank_sessions(tmp_db, "zzzzqqqq")
    assert len(results) == 0


def test_fuzzy_min_score_constant():
    """FUZZY_MIN_SCORE should be high enough to filter partial_ratio noise."""
    assert FUZZY_MIN_SCORE >= 40


def test_frecency_recent_scores_higher():
    now = int(time.time())
    recent = Session("r", "/", "[]", None, None, None, None, None, 0, 0, 0, 0, 0, None, now, now - 3600, None, 1)
    old = Session("o", "/", "[]", None, None, None, None, None, 0, 0, 0, 0, 0, None, now, now - 86400 * 7, None, 1)
    assert frecency_score(recent, now) > frecency_score(old, now)
