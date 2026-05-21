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


class TestProjectRename:
    """Tests for the project rename feature (#31)."""

    def test_start_rename_sets_input_mode(self, tmp_db):
        """Pressing r should activate rename input mode."""
        _insert_session(tmp_db, "s1", "/tmp/project-rename")
        view = ProjectsView(tmp_db)
        view.cursor = 0

        view._start_rename()

        assert view._input_mode == "rename"
        assert view._input_buffer == ""

    def test_start_rename_prefills_existing_name(self, tmp_db):
        """Rename should prefill buffer with existing custom_name."""
        _insert_session(tmp_db, "s1", "/tmp/project-rename")
        tmp_db.execute(
            "INSERT INTO project_favorites (cwd, custom_name) VALUES (?, ?)",
            ("/tmp/project-rename", "My Project"),
        )
        tmp_db.commit()

        view = ProjectsView(tmp_db)
        view.cursor = 0

        view._start_rename()

        assert view._input_mode == "rename"
        assert view._input_buffer == "My Project"

    def test_apply_rename_creates_favorite_with_name(self, tmp_db):
        """Rename should create a project_favorites row if none exists."""
        _insert_session(tmp_db, "s1", "/tmp/project-new")
        view = ProjectsView(tmp_db)
        view.cursor = 0
        view._input_mode = "rename"
        view._input_buffer = "New Name"

        view._apply_rename()

        row = tmp_db.execute(
            "SELECT custom_name FROM project_favorites WHERE cwd = ?",
            ("/tmp/project-new",),
        ).fetchone()
        assert row is not None
        assert row["custom_name"] == "New Name"

    def test_apply_rename_updates_existing_favorite(self, tmp_db):
        """Rename should update custom_name on existing project_favorites row."""
        _insert_session(tmp_db, "s1", "/tmp/project-update")
        tmp_db.execute(
            "INSERT INTO project_favorites (cwd, custom_name) VALUES (?, ?)",
            ("/tmp/project-update", "Old Name"),
        )
        tmp_db.commit()

        view = ProjectsView(tmp_db)
        view.cursor = 0
        view._input_mode = "rename"
        view._input_buffer = "Updated Name"

        view._apply_rename()

        row = tmp_db.execute(
            "SELECT custom_name FROM project_favorites WHERE cwd = ?",
            ("/tmp/project-update",),
        ).fetchone()
        assert row["custom_name"] == "Updated Name"

    def test_apply_rename_clears_name_with_empty_input(self, tmp_db):
        """Rename with empty input should set custom_name to None."""
        _insert_session(tmp_db, "s1", "/tmp/project-clear")
        tmp_db.execute(
            "INSERT INTO project_favorites (cwd, custom_name) VALUES (?, ?)",
            ("/tmp/project-clear", "Old Name"),
        )
        tmp_db.commit()

        view = ProjectsView(tmp_db)
        view.cursor = 0
        view._input_mode = "rename"
        view._input_buffer = ""

        view._apply_rename()

        row = tmp_db.execute(
            "SELECT custom_name FROM project_favorites WHERE cwd = ?",
            ("/tmp/project-clear",),
        ).fetchone()
        assert row["custom_name"] is None

    def test_render_shows_rename_input(self, tmp_db):
        """When in rename mode, the render output should show the rename input."""
        _insert_session(tmp_db, "s1", "/tmp/project-render")
        view = ProjectsView(tmp_db)
        view._input_mode = "rename"
        view._input_buffer = "typing"

        rendered = view.render()
        text = rendered.plain

        assert "rename: typing" in text

    def test_renamed_project_shows_custom_name(self, tmp_db):
        """After renaming, the project should display the custom name."""
        _insert_session(tmp_db, "s1", "/tmp/project-display")
        tmp_db.execute(
            "INSERT INTO project_favorites (cwd, custom_name) VALUES (?, ?)",
            ("/tmp/project-display", "Pretty Name"),
        )
        tmp_db.commit()

        view = ProjectsView(tmp_db)
        rendered = view.render()
        text = rendered.plain

        assert "Pretty Name" in text
