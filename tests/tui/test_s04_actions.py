import pytest
import time

from tests.tui.tmux_controller import TmuxController
from tests.tui.assertions import (
    assert_input_prompt,
    assert_no_input_prompt,
    assert_session_visible,
    assert_session_not_visible,
    assert_favorite_marker,
    assert_no_favorite_marker,
    assert_tag_visible,
    assert_screen_contains,
    assert_empty_state,
)
from tests.tui.seed import seed_for_actions, insert_session


class TestRename:

    def test_rename_mode_activates(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_actions)
        ctrl.send_keys("r")
        screen = ctrl.wait_for("rename:")
        assert_input_prompt(screen, "rename")
        assert_screen_contains(screen, "save")
        assert_screen_contains(screen, "cancel")

    def test_rename_applies(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        ctrl.send_keys("r")
        ctrl.wait_for("rename:")
        for _ in range(len("old-name")):
            ctrl.send_keys("BSpace")
        ctrl.send_text("new-name")
        ctrl.send_keys("Enter")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_no_input_prompt(screen)
        assert_session_visible(screen, "new-name")
        rows = TmuxController.query_db(
            db_path,
            "SELECT custom_name FROM sessions WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert rows[0]["custom_name"] == "new-name"

    def test_rename_escape_cancels(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        ctrl.send_keys("r")
        ctrl.wait_for("rename:")
        ctrl.send_text("should-not-apply")
        ctrl.send_keys("Escape")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_no_input_prompt(screen)
        assert_session_visible(screen, "old-name")
        rows = TmuxController.query_db(
            db_path,
            "SELECT custom_name FROM sessions WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert rows[0]["custom_name"] == "old-name"

    def test_rename_to_empty_clears_name(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        ctrl.send_keys("r")
        ctrl.wait_for("rename:")
        for _ in range(len("old-name")):
            ctrl.send_keys("BSpace")
        ctrl.send_keys("Enter")
        time.sleep(0.5)
        rows = TmuxController.query_db(
            db_path,
            "SELECT custom_name FROM sessions WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert rows[0]["custom_name"] is None

    def test_rename_prefills_existing_name(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_actions)
        ctrl.send_keys("r")
        screen = ctrl.wait_for("rename:")
        assert_screen_contains(screen, "rename: old-name")


class TestTag:

    def test_tag_applies(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        ctrl.send_keys("t")
        ctrl.wait_for("tag:")
        ctrl.send_text("newtag")
        ctrl.send_keys("Enter")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_tag_visible(screen, "newtag")
        rows = TmuxController.query_db(
            db_path,
            "SELECT tag FROM tags WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert any(r["tag"] == "newtag" for r in rows)

    def test_tag_toggles_off(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        ctrl.send_keys("t")
        ctrl.wait_for("tag:")
        ctrl.send_text("toggle")
        ctrl.send_keys("Enter")
        time.sleep(0.3)
        ctrl.send_keys("t")
        ctrl.wait_for("tag:")
        ctrl.send_text("toggle")
        ctrl.send_keys("Enter")
        time.sleep(0.3)
        rows = TmuxController.query_db(
            db_path,
            "SELECT tag FROM tags WHERE session_id = ? AND tag = 'toggle'",
            (sessions["to_rename"],),
        )
        assert len(rows) == 0

    def test_tag_invalid_chars_rejected(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        ctrl.send_keys("t")
        ctrl.wait_for("tag:")
        ctrl.send_text("bad tag!")
        ctrl.send_keys("Enter")
        time.sleep(0.3)
        rows = TmuxController.query_db(
            db_path,
            "SELECT tag FROM tags WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert not any(r["tag"] == "bad tag!" for r in rows)

    def test_tag_empty_rejected(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        ctrl.send_keys("t")
        ctrl.wait_for("tag:")
        ctrl.send_keys("Enter")
        time.sleep(0.3)
        rows = TmuxController.query_db(
            db_path,
            "SELECT COUNT(*) as cnt FROM tags WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert rows[0]["cnt"] == 0


class TestFavorite:

    def test_favorite_toggle_on(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        screen = ctrl.capture()
        assert_no_favorite_marker(screen, "old-name")
        ctrl.send_keys("f")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "★ favorites")
        rows = TmuxController.query_db(
            db_path,
            "SELECT is_favorite FROM sessions WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert rows[0]["is_favorite"] == 1

    def test_favorite_toggle_off(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        ctrl.send_keys("f")
        time.sleep(0.3)
        ctrl.send_keys("f")
        time.sleep(0.3)
        rows = TmuxController.query_db(
            db_path,
            "SELECT is_favorite FROM sessions WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert rows[0]["is_favorite"] == 0


class TestArchive:

    def test_archive_hides_session(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        assert_session_visible(ctrl.capture(), "old-name")
        ctrl.send_keys("u")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_session_not_visible(screen, "old-name")
        rows = TmuxController.query_db(
            db_path,
            "SELECT is_archived FROM sessions WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert rows[0]["is_archived"] == 1


class TestDelete:

    def test_delete_removes_session(self, tui_custom, db_path):
        ctrl, sessions = tui_custom(seed_for_actions)
        assert_session_visible(ctrl.capture(), "old-name")
        ctrl.send_keys("d")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_session_not_visible(screen, "old-name")
        rows = TmuxController.query_db(
            db_path,
            "SELECT COUNT(*) as cnt FROM sessions WHERE session_id = ?",
            (sessions["to_rename"],),
        )
        assert rows[0]["cnt"] == 0

    def test_delete_last_session_shows_empty(self, tui_custom):
        ctrl, _ = tui_custom(lambda conn: insert_session(conn, custom_name="only-one"))
        ctrl.send_keys("d")
        time.sleep(0.5)
        assert_empty_state(ctrl.capture())


class TestSort:

    def test_sort_cycles_in_db(self, tui_custom, db_path):
        ctrl, _ = tui_custom(seed_for_actions)
        ctrl.send_keys("s")
        time.sleep(0.3)
        rows = TmuxController.query_db(db_path, "SELECT value FROM settings WHERE key='sort_mode'")
        assert rows[0]["value"] == "recency"
        ctrl.send_keys("s")
        time.sleep(0.3)
        rows = TmuxController.query_db(db_path, "SELECT value FROM settings WHERE key='sort_mode'")
        assert rows[0]["value"] == "frequency"
        ctrl.send_keys("s")
        time.sleep(0.3)
        rows = TmuxController.query_db(db_path, "SELECT value FROM settings WHERE key='sort_mode'")
        assert rows[0]["value"] == "frecency"

    def test_sort_reorders_sessions(self, tui_custom, db_path):
        ctrl, _ = tui_custom(seed_for_actions)
        ctrl.send_keys("s")
        time.sleep(0.5)
        rows = TmuxController.query_db(db_path, "SELECT value FROM settings WHERE key='sort_mode'")
        assert rows[0]["value"] == "recency"


class TestHideMissing:

    def test_hide_missing_dirs_toggle(self, tui_custom, db_path):
        def seed(conn):
            insert_session(conn, custom_name="existing", cwd="/tmp")
            insert_session(conn, custom_name="missing-dir", cwd="/tmp/nonexistent-xyz-99999")
            return None
        ctrl, _ = tui_custom(seed)
        assert_session_visible(ctrl.capture(), "missing-dir")
        ctrl.send_keys("H")
        time.sleep(0.5)
        assert_session_not_visible(ctrl.capture(), "missing-dir")
        rows = TmuxController.query_db(db_path, "SELECT value FROM settings WHERE key='hide_missing_dirs'")
        assert rows[0]["value"] == "1"
        ctrl.send_keys("H")
        time.sleep(0.5)
        assert_session_visible(ctrl.capture(), "missing-dir")
