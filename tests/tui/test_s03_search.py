import pytest
import time

from tests.tui.assertions import (
    assert_screen_contains,
    assert_screen_not_contains,
    assert_session_visible,
    assert_empty_state,
    assert_tag_visible,
    assert_search_bar_count,
)
from tests.tui.seed import seed_for_search


@pytest.mark.smoke
class TestSearchActivation:

    def test_slash_activates_search(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("/")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, ">")

    def test_typing_filters_sessions(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("auth")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_session_visible(screen, "auth-rewrite")


class TestTagSearch:

    @pytest.mark.xfail(reason="Bug C1: '2' in '#sprint42' triggers view switch instead of typing — see issue #23")
    def test_single_tag_filter(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_search)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("#sprint42")
        time.sleep(1.0)
        screen = ctrl.capture()
        assert_session_visible(screen, "tagged-session")
        assert_search_bar_count(screen, 1, 1)

    @pytest.mark.xfail(reason="Bug C1: '2' and '3' in tag names trigger view switches — see issue #23")
    def test_multi_tag_and_semantics(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_search)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("#sprint42")
        time.sleep(0.5)
        ctrl.send_text(" ")
        time.sleep(0.2)
        ctrl.send_text("#testing")
        time.sleep(1.0)
        screen = ctrl.capture()
        assert_session_visible(screen, "tagged-session")
        assert_search_bar_count(screen, 1, 1)

    def test_tag_filter_no_digits(self, tui_custom):
        """Tag search works when tag name has no digits (avoids C1 bug)."""
        ctrl, _ = tui_custom(seed_for_search)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("#testing")
        time.sleep(1.0)
        screen = ctrl.capture()
        assert_session_visible(screen, "tagged-session")
        assert_search_bar_count(screen, 1, 1)

    def test_nonexistent_tag_shows_empty(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_search)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("#nonexistent-xyz")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_empty_state(screen)


class TestSearchNoResults:

    def test_no_results_shows_message(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_search)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("#zzz-no-match")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_empty_state(screen)


class TestSearchEscape:

    def test_escape_clears_query(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_search)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("#testing")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_search_bar_count(screen, 1, 1)
        ctrl.send_keys("Escape")
        time.sleep(0.3)
        ctrl.send_keys("Escape")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_search_bar_count(screen, 4, 4)

    def test_backspace_in_search(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_search)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("hello")
        time.sleep(0.3)
        ctrl.send_keys("BSpace", "BSpace", "BSpace")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_screen_contains(screen, "> he")


class TestSearchNavigation:

    def test_up_down_during_search(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_search)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_keys("Down")
        time.sleep(0.2)
        ctrl.send_keys("Up")
        time.sleep(0.2)
        screen = ctrl.capture()
        assert_screen_contains(screen, ">")
