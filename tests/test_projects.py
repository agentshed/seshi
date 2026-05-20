import time

from seshi.tui.projects import ProjectsView


def _insert_session(conn, session_id, cwd, last_activity_at=None):
    now = last_activity_at or int(time.time())
    conn.execute(
        "INSERT INTO sessions (session_id, cwd, created_at, last_activity_at) VALUES (?, ?, ?, ?)",
        (session_id, cwd, now, now),
    )
    conn.commit()


def test_singular_session_label(tmp_db):
    """A project with exactly 1 session should display 'session' (singular)."""
    _insert_session(tmp_db, "s1", "/tmp/project-one")

    view = ProjectsView(tmp_db)
    rendered = view.render()
    text = rendered.plain

    assert " 1 session " in text
    assert " 1 sessions" not in text


def test_plural_sessions_label(tmp_db):
    """A project with more than 1 session should display 'sessions' (plural)."""
    _insert_session(tmp_db, "s1", "/tmp/project-two")
    _insert_session(tmp_db, "s2", "/tmp/project-two")

    view = ProjectsView(tmp_db)
    rendered = view.render()
    text = rendered.plain

    assert " 2 sessions" in text
