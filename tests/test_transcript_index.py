import json
import time

from seshi.transcript_index import extract_full_text, index_session, index_pending, search_transcripts


def _make_transcript(path, messages):
    with open(path, "w") as f:
        for role, text in messages:
            obj = {"message": {"role": role, "content": text}}
            f.write(json.dumps(obj) + "\n")


def _make_transcript_blocks(path, messages):
    with open(path, "w") as f:
        for role, blocks in messages:
            obj = {"message": {"role": role, "content": blocks}}
            f.write(json.dumps(obj) + "\n")


def _insert_session(conn, session_id, cwd="/home", ts=None):
    ts = ts or int(time.time())
    conn.execute(
        "INSERT INTO sessions (session_id, cwd, launch_argv_json, created_at, last_activity_at) "
        "VALUES (?, ?, '[]', ?, ?)",
        (session_id, cwd, ts, ts),
    )
    conn.commit()


def test_extract_full_text_simple(tmp_path):
    p = tmp_path / "test.jsonl"
    _make_transcript(p, [
        ("user", "hello world"),
        ("assistant", "hi there"),
    ])
    text = extract_full_text(p)
    assert "hello world" in text
    assert "hi there" in text


def test_extract_full_text_blocks(tmp_path):
    p = tmp_path / "test.jsonl"
    _make_transcript_blocks(p, [
        ("assistant", [
            {"type": "text", "text": "let me check"},
            {"type": "tool_use", "name": "Read", "input": {}},
        ]),
    ])
    text = extract_full_text(p)
    assert "let me check" in text
    assert "Read" not in text


def test_extract_full_text_missing_file(tmp_path):
    p = tmp_path / "nonexistent.jsonl"
    assert extract_full_text(p) == ""


def test_index_session_and_search(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "sess-001.jsonl"
    _make_transcript(transcript, [
        ("user", "fix the authentication bug in the login page"),
        ("assistant", "I found the issue in the auth middleware"),
    ])

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "sess-001" else None,
    )

    _insert_session(tmp_db, "sess-001")
    assert index_session(tmp_db, "sess-001") is True
    tmp_db.commit()

    results = search_transcripts(tmp_db, "authentication")
    assert "sess-001" in results

    results = search_transcripts(tmp_db, "middleware")
    assert "sess-001" in results

    results = search_transcripts(tmp_db, "nonexistent_term_xyz")
    assert "sess-001" not in results


def test_index_session_skips_when_unchanged(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "sess-002.jsonl"
    _make_transcript(transcript, [("user", "hello")])

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "sess-002" else None,
    )

    _insert_session(tmp_db, "sess-002")
    assert index_session(tmp_db, "sess-002") is True
    tmp_db.commit()
    assert index_session(tmp_db, "sess-002") is False


def test_index_session_reindexes_on_size_change(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "sess-003.jsonl"
    _make_transcript(transcript, [("user", "first message")])

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "sess-003" else None,
    )

    _insert_session(tmp_db, "sess-003")
    assert index_session(tmp_db, "sess-003") is True
    tmp_db.commit()

    _make_transcript(transcript, [
        ("user", "first message"),
        ("assistant", "new response with kubernetes deployment"),
    ])
    assert index_session(tmp_db, "sess-003") is True
    tmp_db.commit()

    results = search_transcripts(tmp_db, "kubernetes")
    assert "sess-003" in results


def test_index_pending(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)

    transcripts = {}
    for i in range(3):
        sid = f"sess-10{i}"
        t = project_dir / f"{sid}.jsonl"
        _make_transcript(t, [("user", f"topic {i} discussion")])
        transcripts[sid] = t
        _insert_session(tmp_db, sid)

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcripts.get(sid),
    )

    count = index_pending(tmp_db)
    assert count == 3

    count = index_pending(tmp_db)
    assert count == 0


def test_search_transcripts_prefix(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "sess-020.jsonl"
    _make_transcript(transcript, [
        ("user", "implement the authentication flow"),
    ])

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "sess-020" else None,
    )

    _insert_session(tmp_db, "sess-020")
    index_session(tmp_db, "sess-020")
    tmp_db.commit()

    results = search_transcripts(tmp_db, "auth")
    assert "sess-020" in results


def test_search_transcripts_short_query(tmp_db):
    results = search_transcripts(tmp_db, "a")
    assert results == set()

    results = search_transcripts(tmp_db, "")
    assert results == set()


def test_search_transcripts_special_chars(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "sess-030.jsonl"
    _make_transcript(transcript, [("user", "check the database connection")])

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "sess-030" else None,
    )

    _insert_session(tmp_db, "sess-030")
    index_session(tmp_db, "sess-030")
    tmp_db.commit()

    results = search_transcripts(tmp_db, "database connection")
    assert "sess-030" in results


def test_search_fts5_operators_treated_as_literals(tmp_db, tmp_path, monkeypatch):
    """FTS5 keywords (AND, OR, NOT, NEAR) must be treated as literal search terms."""
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)

    t1 = project_dir / "sess-fts-op1.jsonl"
    _make_transcript(t1, [("user", "the NOT operator is tricky")])
    t2 = project_dir / "sess-fts-op2.jsonl"
    _make_transcript(t2, [("user", "this should not match anything")])

    lookup = {"sess-fts-op1": t1, "sess-fts-op2": t2}
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: lookup.get(sid),
    )

    _insert_session(tmp_db, "sess-fts-op1")
    _insert_session(tmp_db, "sess-fts-op2")
    index_session(tmp_db, "sess-fts-op1")
    index_session(tmp_db, "sess-fts-op2")
    tmp_db.commit()

    results = search_transcripts(tmp_db, "NOT operator")
    assert "sess-fts-op1" in results


def test_search_or_keyword_literal(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "sess-or.jsonl"
    _make_transcript(transcript, [("user", "use OR conditions in the query")])

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "sess-or" else None,
    )

    _insert_session(tmp_db, "sess-or")
    index_session(tmp_db, "sess-or")
    tmp_db.commit()

    results = search_transcripts(tmp_db, "OR conditions")
    assert "sess-or" in results


def test_search_near_keyword_literal(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "sess-near.jsonl"
    _make_transcript(transcript, [("user", "NEAR field communication protocol")])

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "sess-near" else None,
    )

    _insert_session(tmp_db, "sess-near")
    index_session(tmp_db, "sess-near")
    tmp_db.commit()

    results = search_transcripts(tmp_db, "NEAR field")
    assert "sess-near" in results


def test_search_hyphenated_terms(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)
    transcript = project_dir / "sess-hyph.jsonl"
    _make_transcript(transcript, [("user", "fix the api-endpoint for user-auth")])

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "sess-hyph" else None,
    )

    _insert_session(tmp_db, "sess-hyph")
    index_session(tmp_db, "sess-hyph")
    tmp_db.commit()

    results = search_transcripts(tmp_db, "api-endpoint")
    assert "sess-hyph" in results

    results = search_transcripts(tmp_db, "user-auth")
    assert "sess-hyph" in results


def test_search_multi_term(tmp_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "projects" / "test-project"
    project_dir.mkdir(parents=True)

    t1 = project_dir / "sess-040.jsonl"
    _make_transcript(t1, [("user", "fix the react component rendering")])
    t2 = project_dir / "sess-041.jsonl"
    _make_transcript(t2, [("user", "update the python test suite")])

    lookup = {"sess-040": t1, "sess-041": t2}
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: lookup.get(sid),
    )

    _insert_session(tmp_db, "sess-040")
    _insert_session(tmp_db, "sess-041")
    index_session(tmp_db, "sess-040")
    index_session(tmp_db, "sess-041")
    tmp_db.commit()

    results = search_transcripts(tmp_db, "react component")
    assert "sess-040" in results
    assert "sess-041" not in results


# --- extract_full_text edge cases ---


def test_extract_full_text_empty_file(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    assert extract_full_text(p) == ""


def test_extract_full_text_whitespace_only_lines(tmp_path):
    p = tmp_path / "ws.jsonl"
    p.write_text("   \n\n  \n")
    assert extract_full_text(p) == ""


def test_extract_full_text_malformed_json_mixed(tmp_path):
    p = tmp_path / "mixed.jsonl"
    with open(p, "w") as f:
        f.write("not json at all\n")
        f.write(json.dumps({"message": {"role": "user", "content": "valid message"}}) + "\n")
        f.write("{bad json{\n")
        f.write(json.dumps({"message": {"role": "assistant", "content": "also valid"}}) + "\n")
    text = extract_full_text(p)
    assert "valid message" in text
    assert "also valid" in text


def test_extract_full_text_no_message_key(tmp_path):
    p = tmp_path / "nomsg.jsonl"
    with open(p, "w") as f:
        f.write(json.dumps({"timestamp": "2024-01-01", "other": "data"}) + "\n")
        f.write(json.dumps({"message": {"role": "user", "content": "real message"}}) + "\n")
    text = extract_full_text(p)
    assert "real message" in text
    assert "data" not in text


def test_extract_full_text_empty_and_whitespace_content(tmp_path):
    p = tmp_path / "empty_content.jsonl"
    with open(p, "w") as f:
        f.write(json.dumps({"message": {"role": "user", "content": ""}}) + "\n")
        f.write(json.dumps({"message": {"role": "user", "content": "   "}}) + "\n")
        f.write(json.dumps({"message": {"role": "user", "content": "actual text"}}) + "\n")
    text = extract_full_text(p)
    assert "actual text" in text
    assert text.strip() == "actual text"


def test_extract_full_text_null_content(tmp_path):
    p = tmp_path / "null.jsonl"
    with open(p, "w") as f:
        f.write(json.dumps({"message": {"role": "user", "content": None}}) + "\n")
        f.write(json.dumps({"message": {"role": "user"}}) + "\n")
        f.write(json.dumps({"message": {"role": "user", "content": "after null"}}) + "\n")
    text = extract_full_text(p)
    assert "after null" in text


def test_extract_full_text_content_list_empty_text_blocks(tmp_path):
    p = tmp_path / "empty_blocks.jsonl"
    _make_transcript_blocks(p, [
        ("assistant", [
            {"type": "text", "text": ""},
            {"type": "text", "text": "   "},
            {"type": "text", "text": "visible"},
        ]),
    ])
    text = extract_full_text(p)
    assert "visible" in text


def test_extract_full_text_content_list_no_text_blocks(tmp_path):
    p = tmp_path / "tools_only.jsonl"
    _make_transcript_blocks(p, [
        ("assistant", [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            {"type": "tool_result", "content": "file1.py\nfile2.py"},
        ]),
    ])
    assert extract_full_text(p) == ""


def test_extract_full_text_content_list_non_dict_items(tmp_path):
    p = tmp_path / "nondict.jsonl"
    with open(p, "w") as f:
        f.write(json.dumps({"message": {"role": "user", "content": ["just a string", 42, None]}}) + "\n")
        f.write(json.dumps({"message": {"role": "user", "content": "normal text"}}) + "\n")
    text = extract_full_text(p)
    assert "normal text" in text


def test_extract_full_text_mixed_string_and_list(tmp_path):
    p = tmp_path / "mixed_types.jsonl"
    with open(p, "w") as f:
        f.write(json.dumps({"message": {"role": "user", "content": "string content"}}) + "\n")
        f.write(json.dumps({"message": {"role": "assistant", "content": [
            {"type": "text", "text": "list content"},
        ]}}) + "\n")
    text = extract_full_text(p)
    assert "string content" in text
    assert "list content" in text


# --- index_session edge cases ---


def test_index_session_no_transcript(tmp_db, monkeypatch):
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: None,
    )
    _insert_session(tmp_db, "no-transcript")
    assert index_session(tmp_db, "no-transcript") is False


def test_index_session_empty_transcript(tmp_db, tmp_path, monkeypatch):
    transcript = tmp_path / "empty.jsonl"
    transcript.write_text("")
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript,
    )
    _insert_session(tmp_db, "empty-sess")
    assert index_session(tmp_db, "empty-sess") is False


def test_index_session_whitespace_only_transcript(tmp_db, tmp_path, monkeypatch):
    transcript = tmp_path / "ws.jsonl"
    _make_transcript(transcript, [
        ("user", "   "),
        ("assistant", ""),
    ])
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript,
    )
    _insert_session(tmp_db, "ws-sess")
    assert index_session(tmp_db, "ws-sess") is False


def test_index_session_reindex_replaces_old_content(tmp_db, tmp_path, monkeypatch):
    transcript = tmp_path / "evolving.jsonl"
    _make_transcript(transcript, [("user", "quantum computing research")])
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "evolve-001" else None,
    )
    _insert_session(tmp_db, "evolve-001")
    index_session(tmp_db, "evolve-001")
    tmp_db.commit()

    assert "evolve-001" in search_transcripts(tmp_db, "quantum")

    _make_transcript(transcript, [("user", "blockchain development guide")])
    index_session(tmp_db, "evolve-001")
    tmp_db.commit()

    assert "evolve-001" not in search_transcripts(tmp_db, "quantum")
    assert "evolve-001" in search_transcripts(tmp_db, "blockchain")


# --- index_pending edge cases ---


def test_index_pending_no_sessions(tmp_db):
    assert index_pending(tmp_db) == 0


def test_index_pending_skips_archived(tmp_db, tmp_path, monkeypatch):
    transcript = tmp_path / "archived.jsonl"
    _make_transcript(transcript, [("user", "archived content")])
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript,
    )

    ts = int(time.time())
    tmp_db.execute(
        "INSERT INTO sessions (session_id, cwd, launch_argv_json, is_archived, created_at, last_activity_at) "
        "VALUES (?, ?, '[]', 1, ?, ?)",
        ("archived-001", "/home", ts, ts),
    )
    tmp_db.commit()

    assert index_pending(tmp_db) == 0


def test_index_pending_mixed_with_and_without_transcripts(tmp_db, tmp_path, monkeypatch):
    transcript = tmp_path / "has-transcript.jsonl"
    _make_transcript(transcript, [("user", "some content")])

    lookup = {"has-001": transcript}
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: lookup.get(sid),
    )

    _insert_session(tmp_db, "has-001")
    _insert_session(tmp_db, "missing-001")

    count = index_pending(tmp_db)
    assert count == 1
    assert "has-001" in search_transcripts(tmp_db, "some content")


def test_index_pending_reindexes_grown_transcripts(tmp_db, tmp_path, monkeypatch):
    transcript = tmp_path / "growing.jsonl"
    _make_transcript(transcript, [("user", "initial message about python")])

    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "grow-001" else None,
    )

    _insert_session(tmp_db, "grow-001")
    assert index_pending(tmp_db) == 1

    assert "grow-001" in search_transcripts(tmp_db, "python")
    assert "grow-001" not in search_transcripts(tmp_db, "kubernetes")

    _make_transcript(transcript, [
        ("user", "initial message about python"),
        ("assistant", "let me help with kubernetes deployment"),
    ])
    assert index_pending(tmp_db) == 1

    assert "grow-001" in search_transcripts(tmp_db, "kubernetes")


def test_index_pending_fts_not_available(tmp_path):
    import sqlite3
    db_path = tmp_path / "nofts.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, is_archived INTEGER DEFAULT 0);"
    )
    assert index_pending(conn) == 0
    conn.close()


# --- search_transcripts edge cases ---


def test_search_only_special_chars(tmp_db):
    results = search_transcripts(tmp_db, "!@#$%^&*()")
    assert results == set()


def test_search_whitespace_only(tmp_db):
    results = search_transcripts(tmp_db, "   ")
    assert results == set()


def test_search_two_char_boundary(tmp_db, tmp_path, monkeypatch):
    transcript = tmp_path / "boundary.jsonl"
    _make_transcript(transcript, [("user", "database optimization")])
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "bound-001" else None,
    )
    _insert_session(tmp_db, "bound-001")
    index_session(tmp_db, "bound-001")
    tmp_db.commit()

    results = search_transcripts(tmp_db, "db")
    assert isinstance(results, set)


def test_search_porter_stemming(tmp_db, tmp_path, monkeypatch):
    transcript = tmp_path / "stemming.jsonl"
    _make_transcript(transcript, [("user", "the servers are running smoothly")])
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "stem-001" else None,
    )
    _insert_session(tmp_db, "stem-001")
    index_session(tmp_db, "stem-001")
    tmp_db.commit()

    assert "stem-001" in search_transcripts(tmp_db, "run")
    assert "stem-001" in search_transcripts(tmp_db, "runs")


def test_search_case_insensitive(tmp_db, tmp_path, monkeypatch):
    transcript = tmp_path / "case.jsonl"
    _make_transcript(transcript, [("user", "Configure the PostgreSQL database")])
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: transcript if sid == "case-001" else None,
    )
    _insert_session(tmp_db, "case-001")
    index_session(tmp_db, "case-001")
    tmp_db.commit()

    assert "case-001" in search_transcripts(tmp_db, "postgresql")
    assert "case-001" in search_transcripts(tmp_db, "POSTGRESQL")
    assert "case-001" in search_transcripts(tmp_db, "PostgreSQL")


def test_search_empty_fts_table(tmp_db):
    results = search_transcripts(tmp_db, "anything")
    assert results == set()


def test_search_multiple_sessions_match(tmp_db, tmp_path, monkeypatch):
    t1 = tmp_path / "s1.jsonl"
    t2 = tmp_path / "s2.jsonl"
    t3 = tmp_path / "s3.jsonl"
    _make_transcript(t1, [("user", "deploy the kubernetes cluster")])
    _make_transcript(t2, [("user", "kubernetes pod scaling issues")])
    _make_transcript(t3, [("user", "python flask web server")])

    lookup = {"k8s-001": t1, "k8s-002": t2, "flask-001": t3}
    monkeypatch.setattr(
        "seshi.transcript_index.find_transcript_path",
        lambda sid: lookup.get(sid),
    )

    for sid in lookup:
        _insert_session(tmp_db, sid)
        index_session(tmp_db, sid)
    tmp_db.commit()

    results = search_transcripts(tmp_db, "kubernetes")
    assert results == {"k8s-001", "k8s-002"}
    assert "flask-001" not in results


# --- Schema tests ---


def test_fts_tables_created(tmp_db):
    tables = tmp_db.execute(
        "SELECT name FROM sqlite_master WHERE name LIKE 'transcript%' ORDER BY name"
    ).fetchall()
    names = [t["name"] for t in tables]
    assert "transcript_fts" in names
    assert "transcript_index_meta" in names


def test_schema_idempotent(tmp_path):
    import sqlite3
    from seshi.db import init_schema
    db_path = tmp_path / "idempotent.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    init_schema(conn)
    row = conn.execute("SELECT 1 FROM transcript_fts LIMIT 0").fetchone()
    assert row is None
    conn.close()
