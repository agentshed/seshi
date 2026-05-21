import pytest
import time

from tests.tui.assertions import (
    assert_header_visible,
    assert_session_count,
    assert_search_bar_count,
    assert_sort_mode,
    assert_empty_state,
    assert_session_visible,
    assert_footer_shows,
    assert_screen_contains,
)
from tests.tui.seed import insert_session


@pytest.mark.smoke
@pytest.mark.timeout(30)
class TestLaunch:

    def test_header_renders(self, tui):
        ctrl, _ = tui
        screen = ctrl.capture()
        assert_header_visible(screen)
        assert_screen_contains(screen, "v0.1.0")

    def test_tab_bar_visible(self, tui):
        ctrl, _ = tui
        screen = ctrl.capture()
        assert_screen_contains(screen, "1 sessions")
        assert_screen_contains(screen, "2 overview")
        assert_screen_contains(screen, "3 projects")
        assert_screen_contains(screen, "? help")

    def test_search_bar_shows_sort_and_count(self, tui):
        ctrl, session_ids = tui
        screen = ctrl.capture()
        assert_sort_mode(screen, "frecency")
        assert_search_bar_count(screen, len(session_ids), len(session_ids))

    def test_footer_shows_session_keys(self, tui):
        ctrl, _ = tui
        screen = ctrl.capture()
        assert_footer_shows(screen, "resume")
        assert_footer_shows(screen, "rename")
        assert_footer_shows(screen, "fav")
        assert_footer_shows(screen, "tag")
        assert_footer_shows(screen, "delete")
        assert_footer_shows(screen, "sort")
        assert_footer_shows(screen, "search")
        assert_footer_shows(screen, "help")

    def test_session_list_populates(self, tui):
        ctrl, _ = tui
        screen = ctrl.capture()
        named = screen.count_lines_containing("session-")
        assert named > 0, f"Expected named sessions in list.\nScreen:\n{screen.raw}"

    def test_time_bucket_headers(self, tui):
        ctrl, _ = tui
        screen = ctrl.capture()
        assert_screen_contains(screen, "── today ──")


@pytest.mark.smoke
@pytest.mark.timeout(30)
class TestLaunchEmpty:

    def test_empty_database_shows_message(self, tui_empty):
        screen = tui_empty.capture()
        assert_header_visible(screen)
        assert_empty_state(screen)

    def test_empty_database_views_accessible(self, tui_empty):
        ctrl = tui_empty
        ctrl.send_keys("2")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "Totals")

        ctrl.send_keys("3")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "No projects found")


@pytest.mark.smoke
@pytest.mark.timeout(30)
class TestLaunchSingleSession:

    def test_single_session_renders(self, tui_custom):
        def seed(conn):
            return insert_session(conn, custom_name="only-session", first_prompt="The only one")

        ctrl, _ = tui_custom(seed)
        screen = ctrl.capture()
        assert_header_visible(screen)
        assert_session_visible(screen, "only-session")
