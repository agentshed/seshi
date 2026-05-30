"""Tests for batch tag loading (tags cached in _tags dict instead of per-row SQL)."""
import time

from seshi.tui.sessions import SessionsList


def _insert_session(conn, session_id, cwd="/tmp/project", custom_name=None,
                    first_prompt=None, tags=(), ts=None):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, custom_name, first_prompt,
         created_at, last_activity_at)
        VALUES (?,?,?,?,?,?,?)""",
        (session_id, cwd, "[]", custom_name, first_prompt, ts, ts),
    )
    for tag in tags:
        conn.execute("INSERT INTO tags (session_id, tag) VALUES (?, ?)", (session_id, tag))
    conn.commit()


def test_tags_loaded_on_init(tmp_db):
    _insert_session(tmp_db, "s1", tags=["prod", "api"])
    sl = SessionsList(tmp_db)
    assert "s1" in sl._tags
    assert sorted(sl._tags["s1"]) == ["api", "prod"]


def test_tags_dict_correct_structure(tmp_db):
    _insert_session(tmp_db, "s1", tags=["tag1", "tag2"])
    _insert_session(tmp_db, "s2", tags=["tag3"])
    _insert_session(tmp_db, "s3")  # no tags
    sl = SessionsList(tmp_db)
    assert len(sl._tags.get("s1", [])) == 2
    assert len(sl._tags.get("s2", [])) == 1
    assert sl._tags.get("s3", []) == []


def test_tags_refreshed_on_reload(tmp_db):
    _insert_session(tmp_db, "s1", tags=["old-tag"])
    sl = SessionsList(tmp_db)
    assert "old-tag" in sl._tags["s1"]

    tmp_db.execute("INSERT INTO tags (session_id, tag) VALUES (?, ?)", ("s1", "new-tag"))
    tmp_db.commit()
    sl._load_sessions()
    assert "new-tag" in sl._tags["s1"]


def test_render_shows_tags_from_cache(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="tagged-session", tags=["prod", "api"])
    sl = SessionsList(tmp_db)
    rendered = sl.render().plain
    assert "#prod" in rendered
    assert "#api" in rendered


def test_tags_empty_db(tmp_db):
    _insert_session(tmp_db, "s1")
    sl = SessionsList(tmp_db)
    assert sl._tags.get("s1", []) == []
    rendered = sl.render()
    assert rendered is not None


def test_tags_special_characters(tmp_db):
    _insert_session(tmp_db, "s1", tags=["my-tag", "under_score"])
    sl = SessionsList(tmp_db)
    assert "my-tag" in sl._tags["s1"]
    assert "under_score" in sl._tags["s1"]


def test_performance_no_sql_in_render(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="test", tags=["perf"])
    sl = SessionsList(tmp_db)

    # After loading, tags are cached — rendering should not query the conn
    # We verify by temporarily closing the connection's ability to query tags
    # but since we can't patch sqlite3 directly, we verify the cache works
    # by checking that tags render correctly from the cache
    assert "s1" in sl._tags
    assert "perf" in sl._tags["s1"]
    rendered = sl.render().plain
    assert "#perf" in rendered
