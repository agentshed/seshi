import json
import time
from seshi.search import (
    session_resolve, rank_sessions, frecency_score, list_sessions,
    sanitize_query, sanitize_trigram_query, levenshtein, max_edit_distance,
    fuzzy_correct, find_all_positions, find_min_span, count_adjacent_pairs,
    rrf_merge, query_matches_text, blend_search_frecency,
)
from seshi.session_index import index_session_search, extract_vocabulary
from seshi.transcript_index import index_session
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
    index_session_search(conn, session_id)
    conn.commit()


# ── sanitize_query ──


def test_sanitize_query_basic():
    assert sanitize_query("auth") == '"auth"'


def test_sanitize_query_multi_word():
    result = sanitize_query("fix auth bug")
    assert '"auth"' in result
    assert '"bug"' in result


def test_sanitize_query_strips_operators():
    result = sanitize_query("auth AND NOT deploy")
    assert "AND" not in result.replace('"AND"', '')
    assert "NOT" not in result.replace('"NOT"', '')
    assert '"auth"' in result
    assert '"deploy"' in result


def test_sanitize_query_strips_special_chars():
    result = sanitize_query('fix "auth" (bug)')
    assert '"auth"' in result


def test_sanitize_query_empty():
    assert sanitize_query("") == '""'


def test_sanitize_query_whitespace_only():
    assert sanitize_query("   ") == '""'


def test_sanitize_query_only_stopwords():
    result = sanitize_query("the and for")
    assert result != '""'


def test_sanitize_query_mixed_stopwords():
    result = sanitize_query("fix the auth")
    assert '"auth"' in result


def test_sanitize_query_brackets():
    result = sanitize_query("config[0]{key}")
    assert "[" not in result
    assert "]" not in result
    assert "{" not in result
    assert "}" not in result


def test_sanitize_query_asterisk():
    result = sanitize_query("auth*")
    assert "*" not in result


def test_sanitize_query_caret_tilde():
    result = sanitize_query("auth^2 ~deploy")
    assert "^" not in result
    assert "~" not in result


def test_sanitize_query_colons():
    result = sanitize_query("file:auth.py")
    assert ":" not in result


def test_sanitize_query_or_mode():
    result = sanitize_query("auth deploy", mode="OR")
    assert " OR " in result


def test_sanitize_query_dedupes_case_insensitive():
    result = sanitize_query("Auth auth AUTH")
    assert result.lower().count('"auth"') == 1


# ── sanitize_trigram_query ──


def test_sanitize_trigram_basic():
    result = sanitize_trigram_query("auth")
    assert '"auth"' in result


def test_sanitize_trigram_short_tokens_filtered():
    assert sanitize_trigram_query("db") == ""


def test_sanitize_trigram_exactly_3_chars():
    result = sanitize_trigram_query("sql")
    assert '"sql"' in result


def test_sanitize_trigram_mixed_lengths():
    result = sanitize_trigram_query("fix authentication")
    assert '"authentication"' in result


def test_sanitize_trigram_all_short():
    assert sanitize_trigram_query("a b c") == ""


def test_sanitize_trigram_empty():
    assert sanitize_trigram_query("") == ""


def test_sanitize_trigram_special_chars():
    result = sanitize_trigram_query('"auth" [config]')
    assert '"auth"' in result


# ── levenshtein ──


def test_levenshtein_identical():
    assert levenshtein("abc", "abc") == 0


def test_levenshtein_insert():
    assert levenshtein("abc", "abcd") == 1


def test_levenshtein_delete():
    assert levenshtein("abcd", "abc") == 1


def test_levenshtein_replace():
    assert levenshtein("abc", "axc") == 1


def test_levenshtein_empty_a():
    assert levenshtein("", "abc") == 3


def test_levenshtein_empty_b():
    assert levenshtein("abc", "") == 3


def test_levenshtein_both_empty():
    assert levenshtein("", "") == 0


def test_levenshtein_sqlit_sqlite():
    assert levenshtein("sqlit", "sqlite") == 1


# ── max_edit_distance ──


def test_max_edit_distance_short():
    assert max_edit_distance(3) == 1
    assert max_edit_distance(4) == 1


def test_max_edit_distance_medium():
    assert max_edit_distance(5) == 2
    assert max_edit_distance(12) == 2


def test_max_edit_distance_long():
    assert max_edit_distance(13) == 3


# ── fuzzy_correct ──


def test_fuzzy_correct_exact_match(tmp_db):
    conn = tmp_db
    conn.execute("INSERT OR IGNORE INTO vocabulary (word) VALUES (?)", ("sqlite",))
    conn.commit()
    assert fuzzy_correct(conn, "sqlite") is None


def test_fuzzy_correct_one_off(tmp_db):
    conn = tmp_db
    conn.execute("INSERT OR IGNORE INTO vocabulary (word) VALUES (?)", ("sqlite",))
    conn.commit()
    assert fuzzy_correct(conn, "sqlit") == "sqlite"


def test_fuzzy_correct_too_far(tmp_db):
    conn = tmp_db
    conn.execute("INSERT OR IGNORE INTO vocabulary (word) VALUES (?)", ("sqlite",))
    conn.commit()
    assert fuzzy_correct(conn, "sqxyz") is None


def test_fuzzy_correct_short_word(tmp_db):
    assert fuzzy_correct(tmp_db, "sq") is None


def test_fuzzy_correct_no_vocab(tmp_db):
    assert fuzzy_correct(tmp_db, "xyzzyqqq") is None


def test_fuzzy_correct_case_insensitive(tmp_db):
    conn = tmp_db
    conn.execute("INSERT OR IGNORE INTO vocabulary (word) VALUES (?)", ("sqlite",))
    conn.commit()
    assert fuzzy_correct(conn, "SQLIT") == "sqlite"


# ── find_all_positions ──


def test_find_all_positions_basic():
    assert find_all_positions("abcabc", "abc") == [0, 3]


def test_find_all_positions_none():
    assert find_all_positions("abc", "xyz") == []


def test_find_all_positions_single():
    assert find_all_positions("hello world", "world") == [6]


# ── find_min_span ──


def test_find_min_span_basic():
    positions = [[0, 10], [5, 15]]
    assert find_min_span(positions) == 5


def test_find_min_span_empty():
    assert find_min_span([]) == float("inf")


def test_find_min_span_single_list():
    assert find_min_span([[1, 2, 3]]) == 0.0


def test_find_min_span_adjacent():
    positions = [[0], [4]]
    assert find_min_span(positions) == 4


# ── count_adjacent_pairs ──


def test_count_adjacent_pairs_basic():
    positions = [[0], [4]]
    terms = ["fix", "auth"]
    assert count_adjacent_pairs(positions, terms, gap=30) == 1


def test_count_adjacent_pairs_too_far():
    positions = [[0], [100]]
    terms = ["fix", "auth"]
    assert count_adjacent_pairs(positions, terms, gap=30) == 0


def test_count_adjacent_pairs_single_term():
    assert count_adjacent_pairs([[0]], ["fix"]) == 0


def test_count_adjacent_pairs_empty():
    assert count_adjacent_pairs([], []) == 0


# ── rrf_merge ──


def test_rrf_merge_single_source():
    results = rrf_merge([[("a", 0), ("b", 1)]])
    assert results[0][0] == "a"
    assert results[1][0] == "b"
    assert results[0][1] > results[1][1]


def test_rrf_merge_multiple_sources():
    source1 = [("a", 0), ("b", 1)]
    source2 = [("a", 0), ("c", 1)]
    results = rrf_merge([source1, source2])
    ids = [r[0] for r in results]
    assert ids[0] == "a"
    assert "b" in ids
    assert "c" in ids


def test_rrf_merge_disjoint():
    source1 = [("a", 0)]
    source2 = [("b", 0)]
    source3 = [("c", 0)]
    results = rrf_merge([source1, source2, source3])
    ids = [r[0] for r in results]
    assert len(ids) == 3
    assert results[0][1] == results[1][1]  # all same rank → same score


def test_rrf_merge_empty():
    assert rrf_merge([[], [], []]) == []


def test_rrf_merge_duplicate_across_sources():
    source1 = [("a", 0)]
    source2 = [("a", 5)]
    results = rrf_merge([source1, source2])
    assert len(results) == 1
    expected_score = 1.0 / (60 + 0 + 1) + 1.0 / (60 + 5 + 1)
    assert abs(results[0][1] - expected_score) < 1e-10


def test_rrf_merge_single_result():
    results = rrf_merge([[("a", 0)]])
    assert len(results) == 1


def test_rrf_merge_large_result_sets():
    big_list = [(f"s{i}", i) for i in range(50)]
    results = rrf_merge([big_list])
    assert len(results) == 50


# ── query_matches_text ──


def test_query_matches_exact():
    assert query_matches_text("auth", "fix auth bug")


def test_query_matches_case_insensitive():
    assert query_matches_text("AUTH", "fix auth bug")


def test_query_matches_no_match():
    assert not query_matches_text("deploy", "fix auth bug")


def test_query_matches_empty_query():
    assert not query_matches_text("", "fix auth bug")


def test_query_matches_empty_text():
    assert not query_matches_text("auth", "")


def test_query_matches_short_term_filtered():
    assert not query_matches_text("a", "a big thing")


def test_query_matches_any_term():
    assert query_matches_text("auth deploy", "fix auth bug")


def test_query_matches_substring():
    assert query_matches_text("auth", "authentication")


def test_query_matches_unicode():
    assert query_matches_text("café", "the café project")


def test_query_matches_special_chars_in_text():
    assert query_matches_text("auth", "[auth] service")


# ── session_resolve ──


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


# ── rank_sessions (full pipeline) ──


def test_rank_sessions_name_match(tmp_db):
    _insert_session(tmp_db, "id-1", custom_name="auth-rewrite")
    _insert_session(tmp_db, "id-2", first_prompt="fix auth bug")
    _insert_session(tmp_db, "id-3", first_prompt="unrelated work")
    results = rank_sessions(tmp_db, "auth")
    assert len(results) >= 2
    ids = [s.session_id for s, _ in results]
    assert "id-1" in ids
    assert "id-2" in ids


def test_rank_sessions_strips_markup_tags_from_prompt(tmp_db):
    _insert_session(
        tmp_db,
        "id-1",
        first_prompt=(
            "<local-command-caveat>Caveat</local-command-caveat> Open the repo"
        ),
    )
    _insert_session(tmp_db, "id-2", first_prompt="local command checklist")
    results = rank_sessions(tmp_db, "local command")
    ids = [session.session_id for session, _ in results]
    assert "id-2" in ids


def test_rank_sessions_includes_transcript_matches(tmp_db, tmp_path, monkeypatch):
    _insert_session(tmp_db, "fts-1", first_prompt="setup project")
    _insert_session(tmp_db, "fts-2", first_prompt="wrote a haiku poem")

    transcript = tmp_path / "fts-1.jsonl"
    with open(transcript, "w") as f:
        f.write(json.dumps({"message": {"role": "user", "content": "deploy kubernetes cluster"}}) + "\n")

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "fts-1" else None,
    )
    index_session(tmp_db, "fts-1")
    tmp_db.commit()

    results = rank_sessions(tmp_db, "kubernetes")
    ids = [s.session_id for s, _ in results]
    assert "fts-1" in ids
    assert "fts-2" not in ids


def test_rank_sessions_name_outranks_transcript(tmp_db, tmp_path, monkeypatch):
    _insert_session(tmp_db, "name-1", custom_name="kubernetes-deploy")
    _insert_session(tmp_db, "fts-only", first_prompt="generic task")

    transcript = tmp_path / "fts-only.jsonl"
    with open(transcript, "w") as f:
        f.write(json.dumps({"message": {"role": "user", "content": "kubernetes cluster setup"}}) + "\n")

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "fts-only" else None,
    )
    index_session(tmp_db, "fts-only")
    tmp_db.commit()

    results = rank_sessions(tmp_db, "kubernetes")
    ids = [s.session_id for s, _ in results]
    assert "name-1" in ids
    assert "fts-only" in ids
    assert ids.index("name-1") < ids.index("fts-only")


def test_rank_sessions_no_fts_match_still_works(tmp_db):
    _insert_session(tmp_db, "id-a", custom_name="auth-rewrite")
    results = rank_sessions(tmp_db, "auth")
    assert len(results) >= 1
    assert results[0][0].session_id == "id-a"


def test_rank_sessions_no_results_for_gibberish(tmp_db):
    _insert_session(tmp_db, "id-1", custom_name="something")
    results = rank_sessions(tmp_db, "zzzznonexistent")
    assert results == []


def test_rank_sessions_prompt_text_match(tmp_db):
    _insert_session(tmp_db, "prompt-1", first_prompt="unrelated task")
    tmp_db.execute(
        "INSERT INTO prompts (session_id, prompt_index, text) VALUES (?, ?, ?)",
        ("prompt-1", 0, "fix the kubernetes deployment issue"),
    )
    tmp_db.commit()
    index_session_search(tmp_db, "prompt-1")
    tmp_db.commit()
    results = rank_sessions(tmp_db, "kubernetes")
    assert len(results) == 1
    assert results[0][0].session_id == "prompt-1"


# ── False positives (FTS5 token matching should prevent these) ──


def test_sqlite_does_not_match_quite(tmp_db):
    _insert_session(tmp_db, "fp-1", first_prompt="I quite like this approach")
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "fp-1" not in ids


def test_sqlite_does_not_match_suite(tmp_db):
    _insert_session(tmp_db, "fp-2", first_prompt="suite of helpers")
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "fp-2" not in ids


def test_sqlite_does_not_match_site(tmp_db):
    _insert_session(tmp_db, "fp-3", first_prompt="update the site config")
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "fp-3" not in ids


def test_sqlite_does_not_match_write(tmp_db):
    _insert_session(tmp_db, "fp-4", first_prompt="write tests for the API")
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "fp-4" not in ids


def test_sqlite_does_not_match_compile(tmp_db):
    _insert_session(tmp_db, "fp-5", first_prompt="compile the code")
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "fp-5" not in ids


# ── True positives ──


def test_sqlite_matches_exact(tmp_db):
    _insert_session(tmp_db, "tp-1", first_prompt="working with sqlite")
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "tp-1" in ids


def test_sqlite_matches_case_insensitive(tmp_db):
    _insert_session(tmp_db, "tp-2", first_prompt="SQLite migration")
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "tp-2" in ids


def test_sqlite_matches_embedded_via_trigram(tmp_db):
    _insert_session(tmp_db, "tp-3", first_prompt="use pysqlite3 here")
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "tp-3" in ids


def test_sqlite_matches_typo_via_correction(tmp_db):
    _insert_session(tmp_db, "tp-4", first_prompt="fix the sqlite query")
    extract_vocabulary(tmp_db, "sqlite query")
    tmp_db.commit()
    results = rank_sessions(tmp_db, "sqlit")
    ids = [s.session_id for s, _ in results]
    assert "tp-4" in ids


def test_sqlite_matches_in_session_name(tmp_db):
    _insert_session(tmp_db, "tp-5", custom_name="sqlite-migration")
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "tp-5" in ids


def test_sqlite_matches_in_transcript(tmp_db, tmp_path, monkeypatch):
    _insert_session(tmp_db, "tp-6", first_prompt="database work")
    transcript = tmp_path / "tp-6.jsonl"
    with open(transcript, "w") as f:
        f.write(json.dumps({"message": {"role": "user", "content": "migrate the sqlite database"}}) + "\n")
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "tp-6" else None,
    )
    index_session(tmp_db, "tp-6")
    tmp_db.commit()
    results = rank_sessions(tmp_db, "sqlite")
    ids = [s.session_id for s, _ in results]
    assert "tp-6" in ids


# ── Frecency ──


def test_frecency_recent_scores_higher():
    now = int(time.time())
    recent = Session("r", "/", "[]", None, None, None, None, None, 0, 0, 0, 0, 0, None, now, now - 3600, None, 1)
    old = Session("o", "/", "[]", None, None, None, None, None, 0, 0, 0, 0, 0, None, now, now - 86400 * 7, None, 1)
    assert frecency_score(recent, now) > frecency_score(old, now)


# ── blend_search_frecency ──


def test_blend_search_frecency_basic():
    now = int(time.time())
    s1 = Session("a", "/", "[]", None, None, None, None, None, 0, 0, 0, 0, 0, None, now, now, None, 10.0)
    s2 = Session("b", "/", "[]", None, None, None, None, None, 0, 0, 0, 0, 0, None, now, now, None, 1.0)
    scored = [(s1, 1.0, 10.0), (s2, 1.0, 1.0)]
    results = blend_search_frecency(scored)
    assert len(results) == 2
    assert results[0][1] >= results[1][1]


def test_blend_search_frecency_empty():
    assert blend_search_frecency([]) == []


# ── Edge cases: special characters in queries ──


def test_sql_injection_in_query(tmp_db):
    _insert_session(tmp_db, "safe-1", first_prompt="normal session")
    results = rank_sessions(tmp_db, "'; DROP TABLE sessions; --")
    assert isinstance(results, list)
    row = tmp_db.execute("SELECT count(*) as c FROM sessions").fetchone()
    assert row["c"] >= 1


def test_newlines_in_query(tmp_db):
    _insert_session(tmp_db, "nl-1", custom_name="auth-service")
    results = rank_sessions(tmp_db, "auth\nservice")
    ids = [s.session_id for s, _ in results]
    assert "nl-1" in ids


def test_emoji_in_query(tmp_db):
    _insert_session(tmp_db, "emoji-1", first_prompt="deploy rocket")
    results = rank_sessions(tmp_db, "🚀 deploy")
    assert isinstance(results, list)


def test_null_bytes_in_query(tmp_db):
    _insert_session(tmp_db, "null-1", first_prompt="auth service")
    results = rank_sessions(tmp_db, "auth\x00service")
    assert isinstance(results, list)


# ── Edge cases: session indexing ──


def test_index_session_null_name(tmp_db):
    _insert_session(tmp_db, "null-name", first_prompt="some task")
    results = rank_sessions(tmp_db, "task")
    ids = [s.session_id for s, _ in results]
    assert "null-name" in ids


def test_index_session_null_prompt(tmp_db):
    _insert_session(tmp_db, "null-prompt")
    results = rank_sessions(tmp_db, "null-prompt")
    assert isinstance(results, list)


def test_reindex_after_rename(tmp_db):
    _insert_session(tmp_db, "rename-1", custom_name="old-name")
    results = rank_sessions(tmp_db, "old")
    assert any(s.session_id == "rename-1" for s, _ in results)

    tmp_db.execute("UPDATE sessions SET custom_name = 'new-name' WHERE session_id = 'rename-1'")
    tmp_db.commit()
    index_session_search(tmp_db, "rename-1")
    tmp_db.commit()

    results = rank_sessions(tmp_db, "new")
    assert any(s.session_id == "rename-1" for s, _ in results)


# ── Edge cases: filter_cwd ──


def test_rank_sessions_filter_cwd(tmp_db):
    _insert_session(tmp_db, "cwd-1", cwd="/project/a", custom_name="auth-service")
    _insert_session(tmp_db, "cwd-2", cwd="/project/b", custom_name="auth-backend")
    results = rank_sessions(tmp_db, "auth", filter_cwd="/project/a")
    ids = [s.session_id for s, _ in results]
    assert "cwd-1" in ids
    assert "cwd-2" not in ids


# ── Edge cases: multi-term proximity ──


def test_proximity_adjacent_terms_rank_higher(tmp_db):
    _insert_session(tmp_db, "adj-1", first_prompt="fix auth middleware")
    _insert_session(tmp_db, "adj-2", first_prompt="fix something entirely unrelated to auth")
    results = rank_sessions(tmp_db, "fix auth")
    ids = [s.session_id for s, _ in results]
    if len(ids) >= 2:
        assert ids.index("adj-1") < ids.index("adj-2")
