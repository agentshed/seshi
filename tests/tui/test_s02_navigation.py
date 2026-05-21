import pytest
import time

from tests.tui.assertions import assert_session_visible
from tests.tui.seed import seed_for_bulk


@pytest.mark.smoke
class TestCursorMovement:

    def test_j_moves_cursor_down(self, tui_custom):
        ctrl, _ = tui_custom(lambda conn: seed_for_bulk(conn, count=5))
        ctrl.send_keys("j", "j")
        time.sleep(0.3)
        ctrl.send_keys("g")
        time.sleep(0.3)
        screen_top = ctrl.capture()
        assert_session_visible(screen_top, "bulk-0")

    def test_k_at_top_is_noop(self, tui_custom):
        ctrl, _ = tui_custom(lambda conn: seed_for_bulk(conn, count=5))
        ctrl.send_keys("k")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_session_visible(screen, "bulk-0")

    def test_g_jumps_to_top(self, tui_custom):
        ctrl, _ = tui_custom(lambda conn: seed_for_bulk(conn, count=15))
        for _ in range(5):
            ctrl.send_keys("j")
        time.sleep(0.3)
        ctrl.send_keys("g")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_session_visible(screen, "bulk-0")

    def test_G_jumps_to_bottom(self, tui_custom):
        ctrl, _ = tui_custom(lambda conn: seed_for_bulk(conn, count=15))
        ctrl.send_keys("G")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_session_visible(screen, "bulk-14")

    def test_ctrl_d_pages_down(self, tui_custom):
        ctrl, _ = tui_custom(lambda conn: seed_for_bulk(conn, count=20))
        ctrl.send_keys("C-d")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_session_visible(screen, "bulk-10")

    def test_ctrl_u_pages_up(self, tui_custom):
        ctrl, _ = tui_custom(lambda conn: seed_for_bulk(conn, count=20))
        ctrl.send_keys("G")
        time.sleep(0.3)
        ctrl.send_keys("C-u")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_session_visible(screen, "bulk-9")

    def test_arrow_keys_work_like_jk(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("j")
        time.sleep(0.2)
        screen_j = ctrl.capture()
        ctrl.send_keys("k")
        time.sleep(0.2)
        ctrl.send_keys("Down")
        time.sleep(0.2)
        screen_down = ctrl.capture()
        assert screen_j.raw == screen_down.raw
