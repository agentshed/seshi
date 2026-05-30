"""Tests for search scope cycling (Ctrl+O to cycle all/favorites/recent/project)."""
import time

from seshi.tui.search_bar import SearchBar, SCOPES
from seshi.tui.sessions import SessionsList


def _insert_session(conn, session_id, cwd="/tmp/project", custom_name=None,
                    first_prompt=None, is_favorite=0, ts=None):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, custom_name, first_prompt,
         is_favorite, created_at, last_activity_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (session_id, cwd, "[]", custom_name, first_prompt, is_favorite, ts, ts),
    )
    conn.commit()


# --- SearchBar scope tests ---

def test_scope_defaults_to_all():
    bar = SearchBar()
    assert bar.scope == "all"


def test_scope_cycles_correctly():
    bar = SearchBar()
    bar._has_filter_cwd = True
    assert bar.scope == "all"
    bar._cycle_scope()
    assert bar.scope == "favorites"
    bar._cycle_scope()
    assert bar.scope == "recent"
    bar._cycle_scope()
    assert bar.scope == "project"
    bar._cycle_scope()
    assert bar.scope == "all"


def test_scope_skips_project_when_no_cwd():
    bar = SearchBar()
    bar._has_filter_cwd = False
    bar.scope = "recent"
    bar._cycle_scope()
    # Should skip "project" and go to "all"
    assert bar.scope == "all"


def test_scope_display_in_render():
    bar = SearchBar()
    bar.scope = "favorites"
    rendered = bar.render().plain
    assert "favorites" in rendered


def test_scope_not_shown_when_all():
    bar = SearchBar()
    bar.scope = "all"
    rendered = bar.render().plain
    assert "[all]" not in rendered


# --- SessionsList scope filtering tests ---

def test_scope_favorites_filters(tmp_db):
    _insert_session(tmp_db, "s1", is_favorite=1, custom_name="fav-session")
    _insert_session(tmp_db, "s2", is_favorite=0, custom_name="normal-session")
    sl = SessionsList(tmp_db)
    assert len(sl.sessions) == 2

    sl.filter("", scope="favorites")
    assert len(sl.sessions) == 1
    assert sl.sessions[0].is_favorite == 1


def test_scope_recent_filters(tmp_db):
    now = int(time.time())
    _insert_session(tmp_db, "s1", ts=now, custom_name="recent-session")
    _insert_session(tmp_db, "s2", ts=now - 30 * 86400, custom_name="old-session")
    sl = SessionsList(tmp_db)
    assert len(sl.sessions) == 2

    sl.filter("", scope="recent")
    assert len(sl.sessions) == 1
    assert sl.sessions[0].session_id == "s1"


def test_scope_project_filters(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/tmp/projA")
    _insert_session(tmp_db, "s2", cwd="/tmp/projB")
    sl = SessionsList(tmp_db)
    sl.filter_cwd = "/tmp/projA"
    assert len(sl._all_sessions) >= 1

    sl.filter("", scope="project")
    matching = [s for s in sl.sessions if s.cwd == "/tmp/projA"]
    assert len(matching) >= 1
    non_matching = [s for s in sl.sessions if s.cwd != "/tmp/projA"]
    assert len(non_matching) == 0


def test_scope_all_shows_everything(tmp_db):
    _insert_session(tmp_db, "s1", is_favorite=1)
    _insert_session(tmp_db, "s2", is_favorite=0)
    sl = SessionsList(tmp_db)
    sl.filter("", scope="all")
    assert len(sl.sessions) == 2


def test_scope_combined_with_text_search(tmp_db):
    _insert_session(tmp_db, "s1", is_favorite=1, custom_name="auth-rewrite")
    _insert_session(tmp_db, "s2", is_favorite=1, custom_name="bug-fix")
    _insert_session(tmp_db, "s3", is_favorite=0, custom_name="auth-other")
    from seshi.session_index import index_session_search
    for sid in ["s1", "s2", "s3"]:
        index_session_search(tmp_db, sid)
    tmp_db.commit()

    sl = SessionsList(tmp_db)
    sl.filter("auth", scope="favorites")
    names = [s.custom_name for s in sl.sessions]
    assert "auth-rewrite" in names
    assert "auth-other" not in names  # not a favorite


def test_scope_resets_to_all_default(tmp_db):
    _insert_session(tmp_db, "s1", is_favorite=1)
    _insert_session(tmp_db, "s2", is_favorite=0)
    sl = SessionsList(tmp_db)
    sl.filter("", scope="favorites")
    assert len(sl.sessions) == 1

    sl.filter("", scope="all")
    assert len(sl.sessions) == 2


def test_scope_favorites_empty_when_none(tmp_db):
    _insert_session(tmp_db, "s1", is_favorite=0)
    sl = SessionsList(tmp_db)
    sl.filter("", scope="favorites")
    assert len(sl.sessions) == 0


def test_scope_recent_empty_when_all_old(tmp_db):
    old_ts = int(time.time()) - 30 * 86400
    _insert_session(tmp_db, "s1", ts=old_ts)
    sl = SessionsList(tmp_db)
    sl.filter("", scope="recent")
    assert len(sl.sessions) == 0
