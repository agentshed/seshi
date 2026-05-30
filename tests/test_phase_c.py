"""Tests for Phase C TUI UX features: compact mode, project filter, breadcrumb."""
import time

from seshi.tui.sessions import SessionsList
from seshi.tui.footer import Footer
from seshi.db import get_setting, set_setting


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


# === Compact Mode ===


class TestCompactMode:

    def test_compact_mode_defaults_to_off(self, tmp_db):
        view = SessionsList(tmp_db)
        assert view._compact_mode is False

    def test_compact_mode_loaded_from_settings(self, tmp_db):
        set_setting(tmp_db, "compact_mode", "1")
        view = SessionsList(tmp_db)
        assert view._compact_mode is True

    def test_compact_mode_collapses_non_cursor_sessions(self, tmp_db):
        now = int(time.time())
        _insert_session(tmp_db, "s1", custom_name="first", ts=now)
        _insert_session(tmp_db, "s2", custom_name="second", ts=now - 100)
        tmp_db.execute(
            "INSERT INTO prompts (session_id, prompt_index, text, timestamp_epoch) VALUES (?, ?, ?, ?)",
            ("s1", 0, "prompt 1", now),
        )
        tmp_db.execute(
            "INSERT INTO prompts (session_id, prompt_index, text, timestamp_epoch) VALUES (?, ?, ?, ?)",
            ("s2", 0, "prompt 2", now - 100),
        )
        tmp_db.commit()
        view = SessionsList(tmp_db)

        view._compact_mode = True
        view._collapsed = {s.session_id for s in view.sessions}
        s = view.current_session
        if s:
            view._collapsed.discard(s.session_id)
        view._build_display_rows()

        visible_prompt_sids = {r.session.session_id for r in view._display_rows if r.kind == "prompt" and r.session}
        assert visible_prompt_sids == {s.session_id}

    def test_compact_mode_persisted_to_settings(self, tmp_db):
        _insert_session(tmp_db, "s1")
        view = SessionsList(tmp_db)
        view._toggle_compact_mode()
        assert get_setting(tmp_db, "compact_mode") == "1"
        view._toggle_compact_mode()
        assert get_setting(tmp_db, "compact_mode") == "0"

    def test_compact_mode_toggle_preserves_cursor_position(self, tmp_db):
        now = int(time.time())
        for i in range(5):
            _insert_session(tmp_db, f"s{i}", custom_name=f"session-{i}", ts=now - i * 100)
        view = SessionsList(tmp_db)
        view.cursor = 2
        view._toggle_compact_mode()
        assert view.cursor == 2 or view.cursor <= view._nav_row_count() - 1

    def test_compact_mode_init_expands_first_session(self, tmp_db):
        now = int(time.time())
        _insert_session(tmp_db, "s1", custom_name="first", ts=now)
        _insert_session(tmp_db, "s2", custom_name="second", ts=now - 100)
        tmp_db.execute(
            "INSERT INTO prompts (session_id, prompt_index, text, timestamp_epoch) VALUES (?, ?, ?, ?)",
            ("s1", 0, "prompt 1", now),
        )
        tmp_db.execute(
            "INSERT INTO prompts (session_id, prompt_index, text, timestamp_epoch) VALUES (?, ?, ?, ?)",
            ("s2", 0, "prompt 2", now - 100),
        )
        tmp_db.commit()
        set_setting(tmp_db, "compact_mode", "1")
        view = SessionsList(tmp_db)
        visible_prompt_sids = {r.session.session_id for r in view._display_rows if r.kind == "prompt" and r.session}
        assert len(visible_prompt_sids) == 1


# === Quick Project Filter (P key) ===


class TestProjectFilter:

    def test_filter_sets_cwd(self, tmp_db):
        now = int(time.time())
        _insert_session(tmp_db, "s1", cwd="/tmp/projA", custom_name="a1", ts=now)
        _insert_session(tmp_db, "s2", cwd="/tmp/projB", custom_name="b1", ts=now - 100)
        view = SessionsList(tmp_db)
        assert view.filter_cwd is None
        assert len(view.sessions) == 2

        view._filter_to_current_project()
        assert view.filter_cwd is not None
        assert len(view.sessions) == 1

    def test_filter_no_session_no_crash(self, tmp_db):
        view = SessionsList(tmp_db)
        assert view.current_session is None
        view._filter_to_current_project()

    def test_escape_clears_filter(self, tmp_db):
        now = int(time.time())
        _insert_session(tmp_db, "s1", cwd="/tmp/projA", ts=now)
        _insert_session(tmp_db, "s2", cwd="/tmp/projB", ts=now - 100)
        view = SessionsList(tmp_db)
        view._filter_to_current_project()
        assert view.filter_cwd is not None
        view.filter_cwd = None
        view._load_sessions()
        assert len(view.sessions) == 2


# === Footer keys ===


class TestFooterPhaseC:

    def test_footer_shows_compact_key(self):
        footer = Footer()
        footer.view = "sessions"
        rendered = footer.render().plain
        assert "compact" in rendered

    def test_footer_shows_project_key(self):
        footer = Footer()
        footer.view = "sessions"
        rendered = footer.render().plain
        assert "project" in rendered


# === Help text ===


class TestHelpPhaseC:

    def test_help_mentions_compact(self):
        from seshi.tui.help_view import HELP_TEXT
        assert "compact" in HELP_TEXT.lower()

    def test_help_mentions_project_filter(self):
        from seshi.tui.help_view import HELP_TEXT
        assert "Filter to current session" in HELP_TEXT
