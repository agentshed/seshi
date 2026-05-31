"""Tests for SearchBar multi-mode input (search, rename, tag)."""
import time
from unittest.mock import MagicMock

from seshi.tui.search_bar import SearchBar, SearchChanged, InputSubmitted, InputCancelled
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
    from seshi.session_index import index_session_search
    index_session_search(conn, session_id)
    conn.commit()


# === Positive flows ===

def test_search_bar_default_mode():
    bar = SearchBar()
    assert bar.mode == "search"
    assert bar.search_text == ""
    assert bar.active is False


def test_enter_mode_rename():
    bar = SearchBar()
    bar.enter_mode("rename", "old-name")
    assert bar.mode == "rename"
    assert bar.search_text == "old-name"
    assert bar.active is True


def test_enter_mode_tag():
    bar = SearchBar()
    bar.enter_mode("tag")
    assert bar.mode == "tag"
    assert bar.search_text == ""
    assert bar.active is True


def test_exit_mode_restores_search_state():
    bar = SearchBar()
    bar.search_text = "hello"
    bar.scope = "favorites"
    bar.enter_mode("rename", "foo")
    assert bar.search_text == "foo"
    assert bar.mode == "rename"
    bar.exit_mode()
    assert bar.search_text == "hello"
    assert bar.scope == "favorites"
    assert bar.mode == "search"


def test_render_search_prefix():
    bar = SearchBar()
    rendered = bar.render()
    assert "search>" in rendered.plain


def test_render_rename_prefix():
    bar = SearchBar()
    bar.enter_mode("rename", "test")
    rendered = bar.render()
    assert "rename>" in rendered.plain


def test_render_tag_prefix():
    bar = SearchBar()
    bar.enter_mode("tag")
    rendered = bar.render()
    assert "tag>" in rendered.plain


def test_render_hides_counts_in_rename_mode():
    bar = SearchBar()
    bar.shown = 5
    bar.total = 10
    bar.enter_mode("rename", "x")
    rendered = bar.render().plain
    assert "5 / 10" not in rendered


def test_render_shows_counts_in_search_mode():
    bar = SearchBar()
    bar.shown = 5
    bar.total = 10
    rendered = bar.render().plain
    assert "5 / 10" in rendered


def test_render_hides_scope_in_tag_mode():
    bar = SearchBar()
    bar.scope = "favorites"
    bar.enter_mode("tag")
    rendered = bar.render().plain
    assert "[favorites]" not in rendered


# === Cursor blinking ===

def test_cursor_visible_in_rename_mode():
    bar = SearchBar()
    bar.enter_mode("rename", "foo")
    assert bar.active is True
    rendered = bar.render().plain
    assert "_" in rendered


def test_cursor_visible_in_tag_mode():
    bar = SearchBar()
    bar.enter_mode("tag")
    assert bar.active is True
    rendered = bar.render().plain
    assert "_" in rendered


def test_cursor_hidden_after_exit_mode():
    bar = SearchBar()
    bar.enter_mode("rename", "foo")
    bar.exit_mode()
    assert bar.active is False


def test_exit_mode_preserves_active_search():
    bar = SearchBar()
    bar.search_text = "query"
    bar.active = True
    bar.enter_mode("rename", "name")
    assert bar.active is True
    bar.exit_mode()
    assert bar.active is True
    assert bar.search_text == "query"


def test_exit_mode_stays_inactive_if_was_inactive():
    bar = SearchBar()
    bar.active = False
    bar.enter_mode("tag")
    assert bar.active is True
    bar.exit_mode()
    assert bar.active is False


# === Edge cases ===

def test_enter_mode_while_already_in_mode():
    bar = SearchBar()
    bar.search_text = "original-search"
    bar.scope = "recent"
    bar.enter_mode("rename", "name1")
    assert bar.mode == "rename"
    bar.enter_mode("tag")
    assert bar.mode == "tag"
    assert bar.search_text == ""
    bar.exit_mode()
    assert bar.search_text == "name1"
    assert bar.mode == "search"


def test_exit_mode_when_already_in_search():
    bar = SearchBar()
    bar.search_text = "hello"
    bar.exit_mode()
    assert bar.mode == "search"
    assert bar.search_text == "hello"


def test_enter_mode_preserves_empty_search():
    bar = SearchBar()
    bar.enter_mode("rename", "x")
    bar.exit_mode()
    assert bar.search_text == ""
    assert bar.scope == "all"
    assert bar.mode == "search"


def test_rename_prefill_with_special_chars():
    bar = SearchBar()
    bar.enter_mode("rename", "project (v2)")
    assert bar.search_text == "project (v2)"
    rendered = bar.render().plain
    assert "project (v2)" in rendered


# === Negative flows ===

def test_scope_unchanged_in_tag_mode():
    bar = SearchBar()
    bar.scope = "all"
    bar.enter_mode("tag")
    bar._cycle_scope()
    bar._cycle_scope()
    bar.exit_mode()
    assert bar.scope == "all"


# === InputSubmitted / InputCancelled message classes ===

def test_input_submitted_message():
    msg = InputSubmitted("rename", "new-name")
    assert msg.mode == "rename"
    assert msg.text == "new-name"


def test_input_cancelled_message():
    msg = InputCancelled("tag")
    assert msg.mode == "tag"


# === _apply_rename_text / _apply_tag_text integration ===

def test_apply_rename_text_updates_db(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="old")
    view = SessionsList(tmp_db)
    view._apply_rename_text("new")
    row = tmp_db.execute("SELECT custom_name FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["custom_name"] == "new"


def test_apply_rename_text_empty_clears_name(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="old")
    view = SessionsList(tmp_db)
    view._apply_rename_text("")
    row = tmp_db.execute("SELECT custom_name FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["custom_name"] is None


def test_apply_rename_text_whitespace_clears_name(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="old")
    view = SessionsList(tmp_db)
    view._apply_rename_text("   ")
    row = tmp_db.execute("SELECT custom_name FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["custom_name"] is None


def test_apply_tag_text_adds_tag(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._apply_tag_text("prod")
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert any(t["tag"] == "prod" for t in tags)


def test_apply_tag_text_invalid_chars_rejected(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._apply_tag_text("has spaces")
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert len(tags) == 0


def test_apply_tag_text_empty_rejected(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._apply_tag_text("")
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert len(tags) == 0


def test_apply_tag_text_toggles_existing(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._apply_tag_text("prod")
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert len(tags) == 1
    view._apply_tag_text("prod")
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert len(tags) == 0


def test_apply_tag_text_special_chars(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._apply_tag_text("my-tag_v2")
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert any(t["tag"] == "my-tag_v2" for t in tags)


# === Undo integration ===

def test_undo_rename_via_apply_rename_text(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="original")
    view = SessionsList(tmp_db)
    view._apply_rename_text("changed")
    row = tmp_db.execute("SELECT custom_name FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["custom_name"] == "changed"
    assert not view._undo.empty
    entry = view._undo.pop()
    for sql, params in entry.sql_statements:
        tmp_db.execute(sql, params)
    tmp_db.commit()
    row = tmp_db.execute("SELECT custom_name FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["custom_name"] == "original"


def test_undo_tag_via_apply_tag_text(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._apply_tag_text("staging")
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert any(t["tag"] == "staging" for t in tags)
    entry = view._undo.pop()
    for sql, params in entry.sql_statements:
        tmp_db.execute(sql, params)
    tmp_db.commit()
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert not any(t["tag"] == "staging" for t in tags)


# === Notification integration ===

def _make_widget_with_mock_app(tmp_db, session_id="s1", **kwargs):
    _insert_session(tmp_db, session_id, **kwargs)
    sl = SessionsList(tmp_db)
    mock_app = MagicMock()
    mock_app._quit_toast_active = False
    original_app = type(sl).app
    type(sl).app = property(lambda self: mock_app)
    return sl, mock_app, original_app


def test_rename_text_empty_shows_untitled_notification(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db, custom_name="old")
    try:
        sl._apply_rename_text("")
        mock_app.notify.assert_called()
        msg = mock_app.notify.call_args[0][0]
        assert "(untitled)" in msg
    finally:
        type(sl).app = orig


def test_tag_text_toggle_existing_notification(tmp_db):
    sl, mock_app, orig = _make_widget_with_mock_app(tmp_db)
    try:
        sl._apply_tag_text("prod")
        mock_app.notify.reset_mock()
        sl._apply_tag_text("prod")
        mock_app.notify.assert_called_once()
        msg = mock_app.notify.call_args[0][0]
        assert "ntagged" in msg
    finally:
        type(sl).app = orig


# === Project rename via new API ===

def test_project_apply_rename_text(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/tmp/myproject")
    from seshi.tui.projects import ProjectsView
    view = ProjectsView(tmp_db)
    view.cursor = 0
    view._apply_rename_text("My Cool Project")
    row = tmp_db.execute(
        "SELECT custom_name FROM project_favorites WHERE cwd = ?", ("/tmp/myproject",)
    ).fetchone()
    assert row is not None
    assert row["custom_name"] == "My Cool Project"


def test_project_apply_rename_text_clears_name(tmp_db):
    _insert_session(tmp_db, "s1", cwd="/tmp/myproject")
    from seshi.tui.projects import ProjectsView
    view = ProjectsView(tmp_db)
    view.cursor = 0
    view._apply_rename_text("Named")
    view._apply_rename_text("")
    row = tmp_db.execute(
        "SELECT custom_name FROM project_favorites WHERE cwd = ?", ("/tmp/myproject",)
    ).fetchone()
    assert row is not None
    assert row["custom_name"] is None
