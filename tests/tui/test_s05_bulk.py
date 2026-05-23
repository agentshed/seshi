import pytest
import time

from tests.tui.tmux_controller import TmuxController
from tests.tui.assertions import (
    assert_selection_marker,
    assert_no_selection_marker,
    assert_screen_contains,
    assert_screen_not_contains,
    assert_session_visible,
    assert_tag_visible,
)
from tests.tui.seed import seed_for_bulk


class TestBulkSelection:

    def test_space_toggles_selection(self, tui_custom):
        ctrl, ids = tui_custom(lambda conn: seed_for_bulk(conn, count=5))
        ctrl.send_keys("Space")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_selection_marker(screen, "bulk-0")
        ctrl.send_keys("Space")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_no_selection_marker(screen, "bulk-0")

    def test_select_all(self, tui_custom):
        ctrl, _ = tui_custom(lambda conn: seed_for_bulk(conn, count=5))
        ctrl.send_keys("C-a")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert screen.count_lines_containing("[x]") >= 5

    def test_escape_clears_selection(self, tui_custom):
        ctrl, _ = tui_custom(lambda conn: seed_for_bulk(conn, count=5))
        ctrl.send_keys("Space")
        time.sleep(0.2)
        ctrl.send_keys("j")
        time.sleep(0.1)
        ctrl.send_keys("Space")
        time.sleep(0.2)
        screen = ctrl.capture()
        assert screen.count_lines_containing("[x]") >= 2
        ctrl.send_keys("Escape")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert screen.count_lines_containing("[x]") == 0

    def test_bulk_tag(self, tui_custom, db_path):
        ctrl, ids = tui_custom(lambda conn: seed_for_bulk(conn, count=5))
        ctrl.send_keys("Space")
        time.sleep(0.1)
        ctrl.send_keys("j", "Space")
        time.sleep(0.1)
        ctrl.send_keys("j", "Space")
        time.sleep(0.2)
        ctrl.send_keys("t")
        ctrl.wait_for("tag:")
        ctrl.send_text("bulk-tag")
        ctrl.send_keys("Enter")
        time.sleep(0.5)
        rows = TmuxController.query_db(
            db_path,
            "SELECT COUNT(*) as cnt FROM tags WHERE tag = 'bulk-tag'",
        )
        assert rows[0]["cnt"] == 3

    def test_bulk_favorite(self, tui_custom, db_path):
        ctrl, ids = tui_custom(lambda conn: seed_for_bulk(conn, count=5))
        ctrl.send_keys("Space", "j", "Space")
        time.sleep(0.2)
        ctrl.send_keys("f")
        time.sleep(0.5)
        rows = TmuxController.query_db(
            db_path,
            "SELECT COUNT(*) as cnt FROM sessions WHERE is_favorite = 1",
        )
        assert rows[0]["cnt"] == 2


@pytest.mark.regression
class TestBulkConfirmEscape:
    """Bug #65: Escape key must dismiss confirmation dialogs."""

    def test_escape_dismisses_bulk_delete_dialog(self, tui_custom, db_path):
        """Select 2 sessions, press d for bulk delete, press Escape to cancel.

        Bug #65: SeshiApp binds Escape with priority=True, intercepting
        it before the modal's on_key can handle it.
        """
        ctrl, ids = tui_custom(lambda conn: seed_for_bulk(conn, count=5))
        ctrl.send_keys("Space")
        time.sleep(0.1)
        ctrl.send_keys("j", "Space")
        time.sleep(0.2)
        ctrl.send_keys("d")
        ctrl.wait_for("confirm")
        ctrl.send_keys("Escape")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_not_contains(screen, "confirm")
        assert_screen_contains(screen, "bulk-0")
        rows = TmuxController.query_db(
            db_path,
            "SELECT COUNT(*) as cnt FROM sessions",
        )
        assert rows[0]["cnt"] == 5

    def test_escape_dismisses_bulk_archive_dialog(self, tui_custom, db_path):
        """Select 2 sessions, press u for bulk archive, press Escape to cancel.

        Bug #65: same priority binding issue.
        """
        ctrl, ids = tui_custom(lambda conn: seed_for_bulk(conn, count=5))
        ctrl.send_keys("Space")
        time.sleep(0.1)
        ctrl.send_keys("j", "Space")
        time.sleep(0.2)
        ctrl.send_keys("u")
        ctrl.wait_for("confirm")
        ctrl.send_keys("Escape")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_not_contains(screen, "confirm")
        rows = TmuxController.query_db(
            db_path,
            "SELECT COUNT(*) as cnt FROM sessions WHERE is_archived = 0",
        )
        assert rows[0]["cnt"] == 5
