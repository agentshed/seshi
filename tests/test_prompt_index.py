import json
import time

from seshi.prompt_index import index_session_prompts, index_pending_prompts


def _write_jsonl(path, messages):
    path.write_text("\n".join(json.dumps(m) for m in messages) + "\n")


def _insert_session(conn, session_id, cwd="/tmp", ts=None):
    ts = ts or int(time.time())
    conn.execute(
        "INSERT INTO sessions (session_id, cwd, launch_argv_json, created_at, last_activity_at) VALUES (?,?,?,?,?)",
        (session_id, cwd, "[]", ts, ts),
    )
    conn.commit()


def _user_msg(text, timestamp=None, is_meta=False, content=None):
    obj = {"message": {"role": "user", "content": content if content is not None else text}}
    if timestamp:
        obj["timestamp"] = timestamp
    if is_meta:
        obj["isMeta"] = True
    return obj


def _assistant_msg(text, timestamp=None):
    return {"timestamp": timestamp, "message": {"role": "assistant", "content": text}}


def _tool_msg(text, timestamp=None):
    return {"timestamp": timestamp, "message": {"role": "tool", "content": text}}


# ---------- Positive cases ----------


def test_index_session_with_multiple_prompts(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "sess-multi.jsonl"
    msgs = [
        _user_msg(f"prompt number {i}", timestamp=f"2025-01-01T00:0{i}:00Z")
        for i in range(5)
    ]
    # interleave with assistant messages
    all_msgs = []
    for m in msgs:
        all_msgs.append(m)
        all_msgs.append(_assistant_msg("ack"))
    _write_jsonl(p, all_msgs)

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "sess-multi" else None)
    _insert_session(tmp_db, "sess-multi")

    result = index_session_prompts(tmp_db, "sess-multi")
    tmp_db.commit()

    assert result is True
    rows = tmp_db.execute(
        "SELECT prompt_index, text FROM prompts WHERE session_id = ? ORDER BY prompt_index",
        ("sess-multi",),
    ).fetchall()
    assert len(rows) == 5
    for i, row in enumerate(rows):
        assert row["prompt_index"] == i
        assert row["text"] == f"prompt number {i}"


def test_index_filters_to_user_role_only(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "roles.jsonl"
    _write_jsonl(p, [
        _user_msg("user one"),
        _assistant_msg("assistant one"),
        _tool_msg("tool result"),
        _user_msg("user two"),
        _assistant_msg("assistant two"),
    ])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "roles-01" else None)
    _insert_session(tmp_db, "roles-01")

    index_session_prompts(tmp_db, "roles-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT text FROM prompts WHERE session_id = ?", ("roles-01",)).fetchall()
    texts = [r["text"] for r in rows]
    assert texts == ["user one", "user two"]


def test_incremental_reindex_on_file_change(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "incremental.jsonl"
    _write_jsonl(p, [_user_msg("first")])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "inc-01" else None)
    _insert_session(tmp_db, "inc-01")

    assert index_session_prompts(tmp_db, "inc-01") is True
    tmp_db.commit()

    rows = tmp_db.execute("SELECT text FROM prompts WHERE session_id = ?", ("inc-01",)).fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "first"

    # Append new messages (rewrite file with more content)
    _write_jsonl(p, [_user_msg("first"), _assistant_msg("ok"), _user_msg("second")])

    assert index_session_prompts(tmp_db, "inc-01") is True
    tmp_db.commit()

    rows = tmp_db.execute("SELECT text FROM prompts WHERE session_id = ? ORDER BY prompt_index", ("inc-01",)).fetchall()
    assert len(rows) == 2
    assert rows[0]["text"] == "first"
    assert rows[1]["text"] == "second"


def test_index_pending_processes_all_sessions(tmp_db, tmp_path, monkeypatch):
    path_map = {}
    for i in range(3):
        sid = f"pending-{i:03d}"
        p = tmp_path / f"{sid}.jsonl"
        _write_jsonl(p, [_user_msg(f"prompt from session {i}")])
        path_map[sid] = p
        _insert_session(tmp_db, sid)

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: path_map.get(sid))

    count = index_pending_prompts(tmp_db)
    assert count == 3

    for i in range(3):
        sid = f"pending-{i:03d}"
        rows = tmp_db.execute("SELECT text FROM prompts WHERE session_id = ?", (sid,)).fetchall()
        assert len(rows) == 1
        assert rows[0]["text"] == f"prompt from session {i}"


def test_prompt_timestamps_preserved(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "timestamps.jsonl"
    _write_jsonl(p, [
        _user_msg("hello", timestamp="2025-01-01T00:00:00Z"),
        _user_msg("world", timestamp="2025-06-15T12:30:00Z"),
    ])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "ts-01" else None)
    _insert_session(tmp_db, "ts-01")

    index_session_prompts(tmp_db, "ts-01")
    tmp_db.commit()

    rows = tmp_db.execute(
        "SELECT text, timestamp_epoch FROM prompts WHERE session_id = ? ORDER BY prompt_index",
        ("ts-01",),
    ).fetchall()
    assert len(rows) == 2
    # 2025-01-01T00:00:00Z = 1735689600
    assert rows[0]["timestamp_epoch"] == 1735689600
    # 2025-06-15T12:30:00Z = 1750000200
    assert rows[1]["timestamp_epoch"] is not None
    assert rows[1]["timestamp_epoch"] > rows[0]["timestamp_epoch"]


# ---------- Negative cases ----------


def test_index_session_no_transcript(tmp_db, monkeypatch):
    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: None)
    _insert_session(tmp_db, "no-transcript")

    result = index_session_prompts(tmp_db, "no-transcript")
    assert result is False

    rows = tmp_db.execute("SELECT * FROM prompts WHERE session_id = ?", ("no-transcript",)).fetchall()
    assert len(rows) == 0


def test_index_empty_transcript(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "empty.jsonl"
    p.write_text("")

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "empty-01" else None)
    _insert_session(tmp_db, "empty-01")

    result = index_session_prompts(tmp_db, "empty-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT * FROM prompts WHERE session_id = ?", ("empty-01",)).fetchall()
    assert len(rows) == 0


def test_index_transcript_only_meta(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "meta.jsonl"
    _write_jsonl(p, [
        _user_msg("system caveat", is_meta=True),
        _user_msg("another meta", is_meta=True),
    ])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "meta-01" else None)
    _insert_session(tmp_db, "meta-01")

    index_session_prompts(tmp_db, "meta-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT * FROM prompts WHERE session_id = ?", ("meta-01",)).fetchall()
    assert len(rows) == 0


def test_index_transcript_only_assistant_messages(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "assistant-only.jsonl"
    _write_jsonl(p, [
        _assistant_msg("I can help with that"),
        _assistant_msg("Here is the answer"),
    ])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "asst-01" else None)
    _insert_session(tmp_db, "asst-01")

    index_session_prompts(tmp_db, "asst-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT * FROM prompts WHERE session_id = ?", ("asst-01",)).fetchall()
    assert len(rows) == 0


def test_index_transcript_malformed_json(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "malformed.jsonl"
    lines = [
        "not valid json at all",
        json.dumps(_user_msg("valid prompt one")),
        "{broken json{{{",
        json.dumps(_user_msg("valid prompt two")),
        "",
    ]
    p.write_text("\n".join(lines) + "\n")

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "bad-01" else None)
    _insert_session(tmp_db, "bad-01")

    result = index_session_prompts(tmp_db, "bad-01")
    tmp_db.commit()

    assert result is True
    rows = tmp_db.execute("SELECT text FROM prompts WHERE session_id = ? ORDER BY prompt_index", ("bad-01",)).fetchall()
    assert len(rows) == 2
    assert rows[0]["text"] == "valid prompt one"
    assert rows[1]["text"] == "valid prompt two"


# ---------- Edge cases ----------


def test_prompt_text_truncation(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "long.jsonl"
    long_text = "x" * 1200
    _write_jsonl(p, [_user_msg(long_text)])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "long-01" else None)
    _insert_session(tmp_db, "long-01")

    index_session_prompts(tmp_db, "long-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT text FROM prompts WHERE session_id = ?", ("long-01",)).fetchall()
    assert len(rows) == 1
    assert len(rows[0]["text"]) == 500


def test_prompt_unicode_emoji(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "unicode.jsonl"
    _write_jsonl(p, [
        _user_msg("CJK text here"),
        _user_msg("emoji test here"),
        _user_msg("RTL text here"),
    ])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "uni-01" else None)
    _insert_session(tmp_db, "uni-01")

    index_session_prompts(tmp_db, "uni-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT text FROM prompts WHERE session_id = ? ORDER BY prompt_index", ("uni-01",)).fetchall()
    assert len(rows) == 3
    assert "CJK" in rows[0]["text"]
    assert "emoji" in rows[1]["text"]
    assert "RTL" in rows[2]["text"]


def test_prompt_with_newlines(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "newlines.jsonl"
    _write_jsonl(p, [_user_msg("line one\nline two\nline three")])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "nl-01" else None)
    _insert_session(tmp_db, "nl-01")

    index_session_prompts(tmp_db, "nl-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT text FROM prompts WHERE session_id = ?", ("nl-01",)).fetchall()
    assert len(rows) == 1
    assert "\n" not in rows[0]["text"]
    assert "line one line two line three" == rows[0]["text"]


def test_idempotent_indexing(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "idempotent.jsonl"
    _write_jsonl(p, [_user_msg("hello"), _user_msg("world")])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "idem-01" else None)
    _insert_session(tmp_db, "idem-01")

    assert index_session_prompts(tmp_db, "idem-01") is True
    tmp_db.commit()

    # Second call without file change should return False
    assert index_session_prompts(tmp_db, "idem-01") is False

    rows = tmp_db.execute("SELECT * FROM prompts WHERE session_id = ?", ("idem-01",)).fetchall()
    assert len(rows) == 2


def test_cascade_delete_prompts(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "cascade.jsonl"
    _write_jsonl(p, [_user_msg("to be deleted")])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "cas-01" else None)
    _insert_session(tmp_db, "cas-01")

    index_session_prompts(tmp_db, "cas-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT * FROM prompts WHERE session_id = ?", ("cas-01",)).fetchall()
    assert len(rows) == 1

    # Delete the session; CASCADE should remove prompts
    tmp_db.execute("DELETE FROM sessions WHERE session_id = ?", ("cas-01",))
    tmp_db.commit()

    rows = tmp_db.execute("SELECT * FROM prompts WHERE session_id = ?", ("cas-01",)).fetchall()
    assert len(rows) == 0


def test_prompt_with_array_content(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "array-content.jsonl"
    _write_jsonl(p, [
        _user_msg(None, content=[{"type": "text", "text": "extracted from array"}]),
    ])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "arr-01" else None)
    _insert_session(tmp_db, "arr-01")

    index_session_prompts(tmp_db, "arr-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT text FROM prompts WHERE session_id = ?", ("arr-01",)).fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "extracted from array"


def test_index_session_with_zero_user_messages(tmp_db, tmp_path, monkeypatch):
    p = tmp_path / "no-user.jsonl"
    _write_jsonl(p, [
        {"message": {"role": "system", "content": "You are helpful"}},
        _assistant_msg("Hello, how can I help?"),
    ])

    monkeypatch.setattr("seshi.prompt_index.find_transcript_path", lambda sid: p if sid == "nousers-01" else None)
    _insert_session(tmp_db, "nousers-01")

    index_session_prompts(tmp_db, "nousers-01")
    tmp_db.commit()

    rows = tmp_db.execute("SELECT * FROM prompts WHERE session_id = ?", ("nousers-01",)).fetchall()
    assert len(rows) == 0
