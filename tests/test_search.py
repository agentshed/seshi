import json
import time
from seshi.search import fuzzy_match, session_resolve, rank_sessions, frecency_score, list_sessions
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
            "<local-command-caveat>Caveat</local-command-caveat> Open the repo"
        ),
    )
    _insert_session(tmp_db, "id-2", first_prompt="local command checklist")

    results = rank_sessions(tmp_db, "local command")

    ids = [session.session_id for session, _ in results]
    assert "id-2" in ids
    assert "id-1" not in ids


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


def test_frecency_recent_scores_higher():
    now = int(time.time())
    recent = Session("r", "/", "[]", None, None, None, None, None, 0, 0, 0, 0, 0, None, now, now - 3600, None, 1)
    old = Session("o", "/", "[]", None, None, None, None, None, 0, 0, 0, 0, 0, None, now, now - 86400 * 7, None, 1)
    assert frecency_score(recent, now) > frecency_score(old, now)


def test_score_sessions_matches_prompt_text(tmp_db):
    from seshi.search import score_sessions
    _insert_session(tmp_db, "prompt-1", first_prompt="unrelated task")
    prompt_texts = {"prompt-1": ["fix the kubernetes deployment issue"]}
    results = score_sessions(
        [Session.from_row(tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'prompt-1'").fetchone())],
        "kubernetes",
        {},
        prompt_texts,
    )
    assert len(results) == 1
    assert results[0][0].session_id == "prompt-1"


def test_prompt_match_boosts_session_ranking(tmp_db):
    from seshi.search import score_sessions
    _insert_session(tmp_db, "name-match", custom_name="kubernetes-deploy")
    _insert_session(tmp_db, "prompt-match", first_prompt="unrelated")
    sessions = [
        Session.from_row(tmp_db.execute("SELECT * FROM sessions WHERE session_id = ?", (sid,)).fetchone())
        for sid in ("name-match", "prompt-match")
    ]
    prompt_texts = {"prompt-match": ["deploy the kubernetes cluster"]}
    results = score_sessions(sessions, "kubernetes", {}, prompt_texts)
    ids = [s.session_id for s, _ in results]
    assert "name-match" in ids
    assert "prompt-match" in ids


def test_no_prompt_match_for_gibberish(tmp_db):
    from seshi.search import score_sessions
    _insert_session(tmp_db, "normal", first_prompt="normal task")
    sessions = [Session.from_row(tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'normal'").fetchone())]
    prompt_texts = {"normal": ["do something useful"]}
    results = score_sessions(sessions, "xyzzy123qqq", {}, prompt_texts)
    assert len(results) == 0


def test_prompt_match_and_session_name_combined(tmp_db):
    from seshi.search import score_sessions
    _insert_session(tmp_db, "both-match", custom_name="kubernetes-setup", first_prompt="unrelated")
    _insert_session(tmp_db, "name-only", custom_name="kubernetes-config")
    sessions = [
        Session.from_row(tmp_db.execute("SELECT * FROM sessions WHERE session_id = ?", (sid,)).fetchone())
        for sid in ("both-match", "name-only")
    ]
    prompt_texts = {"both-match": ["configure the kubernetes ingress"]}
    results = score_sessions(sessions, "kubernetes", {}, prompt_texts)
    scores = {s.session_id: score for s, score in results}
    assert scores.get("both-match", 0) >= scores.get("name-only", 0)
