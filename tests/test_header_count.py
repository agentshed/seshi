"""Tests for _all_sessions vs sessions count after filtering (issue #30)."""

import time

from seshi.tui.sessions import SessionsList


def _insert_sessions(conn, names):
    """Insert sessions with the given custom_names and return their IDs."""
    ts = int(time.time())
    ids = []
    for i, name in enumerate(names):
        sid = f"sess-{i}"
        conn.execute(
            "INSERT INTO sessions "
            "(session_id, cwd, launch_argv_json, custom_name, first_prompt, "
            "created_at, last_activity_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (sid, "/tmp", "[]", name, None, ts - i, ts - i),
        )
        ids.append(sid)
    conn.commit()
    return ids


def test_all_sessions_preserves_total_after_query(tmp_db):
    """_all_sessions must contain all sessions, not just filtered ones."""
    # Use names where only one has a unique substring "zzxyq"
    names = ["zzxyq-unique", "normal-one", "normal-two", "normal-three", "normal-four"]
    _insert_sessions(tmp_db, names)
    widget = SessionsList(tmp_db)

    # Before filtering: both lists have all 5 sessions
    assert len(widget._all_sessions) == 5
    assert len(widget.sessions) == 5

    # Filter with a query that should narrow results
    widget._load_sessions(query="zzxyq")

    # _all_sessions must still reflect the total (unfiltered) count
    assert len(widget._all_sessions) == 5
    # sessions should be fewer than the total
    assert len(widget.sessions) < len(widget._all_sessions)
    # The unique match must be present
    matched_names = [s.custom_name for s in widget.sessions]
    assert "zzxyq-unique" in matched_names


def test_all_sessions_equals_shown_without_query(tmp_db):
    """Without a query, _all_sessions and sessions should be equal."""
    _insert_sessions(tmp_db, ["aaa", "bbb", "ccc"])
    widget = SessionsList(tmp_db)

    widget._load_sessions()

    assert len(widget._all_sessions) == 3
    assert len(widget.sessions) == 3
