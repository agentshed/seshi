"""Tests for the undo stack (Item 12)."""
import time

from seshi.tui.undo import UndoStack, UndoEntry
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


# === UndoStack unit tests ===

def test_undo_stack_push_and_pop():
    stack = UndoStack()
    e1 = UndoEntry(action="rename", description="Renamed to foo", sql_statements=[])
    e2 = UndoEntry(action="tag", description="Tag #prod", sql_statements=[])
    e3 = UndoEntry(action="favorite", description="Favorited", sql_statements=[])
    stack.push(e1)
    stack.push(e2)
    stack.push(e3)
    assert stack.pop() is e3
    assert stack.pop() is e2
    assert stack.pop() is e1


def test_undo_stack_max_size():
    stack = UndoStack()
    for i in range(15):
        stack.push(UndoEntry(action="rename", description=f"action-{i}", sql_statements=[]))
    assert len(stack) == 10
    last = stack.pop()
    assert last.description == "action-14"


def test_undo_stack_empty_pop():
    stack = UndoStack()
    assert stack.pop() is None


def test_undo_stack_empty_property():
    stack = UndoStack()
    assert stack.empty is True
    stack.push(UndoEntry(action="rename", description="test", sql_statements=[]))
    assert stack.empty is False


# === Integration with SessionsList ===

def test_undo_rename_restores_old_name(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="original")
    view = SessionsList(tmp_db)
    view._input_mode = "rename"
    view._input_buffer = "new-name"
    view._apply_rename()
    row = tmp_db.execute("SELECT custom_name FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["custom_name"] == "new-name"
    assert not view._undo.empty

    entry = view._undo.pop()
    for sql, params in entry.sql_statements:
        tmp_db.execute(sql, params)
    tmp_db.commit()
    row = tmp_db.execute("SELECT custom_name FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["custom_name"] == "original"


def test_undo_tag_removes_added_tag(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._input_mode = "tag"
    view._input_buffer = "prod"
    view._apply_tag()
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert any(t["tag"] == "prod" for t in tags)

    entry = view._undo.pop()
    for sql, params in entry.sql_statements:
        tmp_db.execute(sql, params)
    tmp_db.commit()
    tags = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchall()
    assert not any(t["tag"] == "prod" for t in tags)


def test_undo_favorite_toggles_back(tmp_db):
    _insert_session(tmp_db, "s1", is_favorite=0)
    view = SessionsList(tmp_db)
    view._toggle_favorite()
    row = tmp_db.execute("SELECT is_favorite FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["is_favorite"] == 1

    entry = view._undo.pop()
    for sql, params in entry.sql_statements:
        tmp_db.execute(sql, params)
    tmp_db.commit()
    row = tmp_db.execute("SELECT is_favorite FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["is_favorite"] == 0


def test_undo_archive_restores_visibility(tmp_db):
    _insert_session(tmp_db, "s1")
    view = SessionsList(tmp_db)
    view._execute_archive(["s1"])
    row = tmp_db.execute("SELECT is_archived FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["is_archived"] == 1

    entry = view._undo.pop()
    for sql, params in entry.sql_statements:
        tmp_db.execute(sql, params)
    tmp_db.commit()
    row = tmp_db.execute("SELECT is_archived FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row["is_archived"] == 0


def test_undo_delete_restores_session(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="to-delete")
    tmp_db.execute("INSERT INTO tags (session_id, tag) VALUES (?, ?)", ("s1", "important"))
    tmp_db.commit()
    view = SessionsList(tmp_db)
    view._execute_delete(["s1"])
    row = tmp_db.execute("SELECT 1 FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row is None

    entry = view._undo.pop()
    for sql, params in entry.sql_statements:
        tmp_db.execute(sql, params)
    tmp_db.commit()
    row = tmp_db.execute("SELECT custom_name FROM sessions WHERE session_id = ?", ("s1",)).fetchone()
    assert row is not None
    assert row["custom_name"] == "to-delete"
    tag = tmp_db.execute("SELECT tag FROM tags WHERE session_id = ?", ("s1",)).fetchone()
    assert tag is not None
    assert tag["tag"] == "important"


def test_multiple_undo_operations(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="orig")
    view = SessionsList(tmp_db)

    view._input_mode = "rename"
    view._input_buffer = "renamed"
    view._apply_rename()

    view._input_mode = "tag"
    view._input_buffer = "prod"
    view._apply_tag()

    view._toggle_favorite()

    assert len(view._undo) == 3


def test_undo_entry_has_description():
    entry = UndoEntry(action="rename", description="Renamed to foo", sql_statements=[])
    assert entry.description == "Renamed to foo"
    assert entry.action == "rename"
