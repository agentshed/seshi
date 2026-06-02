import json
import time
from seshi.drain import drain_queue


def _write_queue(tmp_path, events):
    from unittest import mock
    q = tmp_path / "queue.jsonl"
    q.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return q


def test_start_event_inserts(tmp_db, tmp_path):
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "abc-123", "cwd": "/home", "argv": "claude"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        count = drain_queue(tmp_db)
    assert count == 1
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'abc-123'").fetchone()
    assert row is not None
    assert row["cwd"] == "/home"


def test_stop_event_updates(tmp_db, tmp_path):
    from unittest import mock
    ts = int(time.time())
    tmp_db.execute(
        "INSERT INTO sessions (session_id, cwd, launch_argv_json, created_at, last_activity_at) VALUES (?,?,?,?,?)",
        ("abc-123", "/home", "[]", ts, ts),
    )
    tmp_db.commit()
    q = _write_queue(tmp_path, [
        {"event": "stop", "ts": ts + 100, "session_id": "abc-123", "message_count": 42, "token_count": 5000, "first_prompt": "hello"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'abc-123'").fetchone()
    assert row["message_count"] == 42
    assert row["token_count"] == 5000
    assert row["status"] == "done"


def test_idempotent_start(tmp_db, tmp_path):
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "abc-123", "cwd": "/home", "argv": "claude"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    tmp_db.execute("UPDATE sessions SET custom_name = 'my-session' WHERE session_id = 'abc-123'")
    tmp_db.commit()
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "abc-123", "cwd": "/home", "argv": "claude"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    row = tmp_db.execute("SELECT custom_name FROM sessions WHERE session_id = 'abc-123'").fetchone()
    assert row["custom_name"] == "my-session"


def test_malformed_line_skipped(tmp_db, tmp_path):
    from unittest import mock
    q = tmp_path / "queue.jsonl"
    q.write_text("not json\n" + json.dumps({"event": "start", "ts": 1000, "session_id": "ok-1", "cwd": "/x", "argv": "c"}) + "\n")
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        count = drain_queue(tmp_db)
    assert count == 1


def test_missing_queue_noop(tmp_db, tmp_path):
    from unittest import mock
    q = tmp_path / "nonexistent.jsonl"
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        count = drain_queue(tmp_db)
    assert count == 0


def test_stop_for_unknown_session(tmp_db, tmp_path):
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "stop", "ts": 1000, "session_id": "unknown-1", "message_count": 5, "token_count": 100},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        count = drain_queue(tmp_db)
    assert count == 1
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'unknown-1'").fetchone()
    assert row is None


def test_first_prompt_coalesce(tmp_db, tmp_path):
    from unittest import mock
    ts = int(time.time())
    tmp_db.execute(
        "INSERT INTO sessions (session_id, cwd, launch_argv_json, first_prompt, created_at, last_activity_at) VALUES (?,?,?,?,?,?)",
        ("abc-123", "/home", "[]", "original prompt", ts, ts),
    )
    tmp_db.commit()
    q = _write_queue(tmp_path, [
        {"event": "stop", "ts": ts + 100, "session_id": "abc-123", "message_count": 10, "token_count": 500, "first_prompt": "new prompt"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    row = tmp_db.execute("SELECT first_prompt FROM sessions WHERE session_id = 'abc-123'").fetchone()
    assert row["first_prompt"] == "original prompt"


def test_queue_truncated_after_drain(tmp_db, tmp_path):
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "abc-123", "cwd": "/home", "argv": "c"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    assert q.read_text() == ""


def test_empty_queue(tmp_db, tmp_path):
    from unittest import mock
    q = tmp_path / "queue.jsonl"
    q.write_text("")
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        count = drain_queue(tmp_db)
    assert count == 0


def test_drain_deletes_empty_session_on_stop(tmp_db, tmp_path):
    """Start followed by stop with message_count=0 and no prompt deletes the row."""
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "empty-1", "cwd": "/home", "argv": "claude"},
        {"event": "stop", "ts": 1001, "session_id": "empty-1", "message_count": 0, "token_count": 0},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        count = drain_queue(tmp_db)
    assert count == 2
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'empty-1'").fetchone()
    assert row is None


def test_drain_keeps_session_with_messages(tmp_db, tmp_path):
    """Stop with message_count > 0 updates the row normally."""
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "active-1", "cwd": "/home", "argv": "claude"},
        {"event": "stop", "ts": 1001, "session_id": "active-1", "message_count": 5, "token_count": 200, "first_prompt": "hello"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'active-1'").fetchone()
    assert row is not None
    assert row["message_count"] == 5
    assert row["status"] == "done"


def test_drain_deletes_preexisting_empty_session(tmp_db, tmp_path):
    """Pre-existing session row deleted when stop arrives with no activity."""
    from unittest import mock
    ts = int(time.time())
    tmp_db.execute(
        "INSERT INTO sessions (session_id, cwd, launch_argv_json, created_at, last_activity_at) VALUES (?,?,?,?,?)",
        ("pre-1", "/home", "[]", ts, ts),
    )
    tmp_db.commit()
    q = _write_queue(tmp_path, [
        {"event": "stop", "ts": ts + 100, "session_id": "pre-1", "message_count": 0, "token_count": 0},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'pre-1'").fetchone()
    assert row is None


def test_drain_stop_null_message_count_deletes(tmp_db, tmp_path):
    """A stop event with message_count=None and no first_prompt should delete the session."""
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "null-mc-1", "cwd": "/home", "argv": "claude"},
        {"event": "stop", "ts": 1001, "session_id": "null-mc-1", "message_count": None, "token_count": 0},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        count = drain_queue(tmp_db)
    assert count == 2
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'null-mc-1'").fetchone()
    assert row is None


def test_drain_stop_null_message_count_with_prompt_updates(tmp_db, tmp_path):
    """A stop event with message_count=None but a valid first_prompt should update, not delete."""
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "null-mc-2", "cwd": "/home", "argv": "claude"},
        {"event": "stop", "ts": 1001, "session_id": "null-mc-2", "message_count": None, "token_count": 0, "first_prompt": "hello"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'null-mc-2'").fetchone()
    assert row is not None
    assert row["status"] == "done"
    assert row["first_prompt"] == "hello"


def test_drain_stop_null_token_count_stores_zero(tmp_db, tmp_path):
    """A stop event with token_count=None should store 0, not NULL."""
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "null-tokens-1", "cwd": "/home", "argv": "claude"},
        {"event": "stop", "ts": 1001, "session_id": "null-tokens-1", "message_count": 1, "token_count": None, "first_prompt": "hello"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    row = tmp_db.execute("SELECT token_count FROM sessions WHERE session_id = 'null-tokens-1'").fetchone()
    assert row["token_count"] == 0


def test_drain_keeps_session_with_first_prompt_only(tmp_db, tmp_path):
    """Stop with message_count=0 but a first_prompt keeps the session."""
    from unittest import mock
    q = _write_queue(tmp_path, [
        {"event": "start", "ts": 1000, "session_id": "prompt-1", "cwd": "/home", "argv": "claude"},
        {"event": "stop", "ts": 1001, "session_id": "prompt-1", "message_count": 0, "token_count": 0, "first_prompt": "help me"},
    ])
    with mock.patch("seshi.drain.QUEUE_PATH", q):
        drain_queue(tmp_db)
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'prompt-1'").fetchone()
    assert row is not None
    assert row["first_prompt"] == "help me"
