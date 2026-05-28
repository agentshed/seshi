"""TUI integration tests: `seshi <query>` opens TUI with pre-populated search."""

import time

import pytest

from tests.tui.assertions import (
    assert_empty_state,
    assert_screen_contains,
    assert_search_bar_count,
    assert_session_visible,
)
from tests.tui.seed import seed_for_search


@pytest.mark.smoke
class TestQueryPrePopulatesSearch:

    def test_query_appears_in_search_bar(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="auth")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "> auth")
        assert_session_visible(screen, "auth-rewrite")

    def test_query_filters_results(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="auth")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_search_bar_count(screen, 1, 4)

    def test_user_can_refine_query(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="auth")
        time.sleep(0.5)
        ctrl.send_text("-rewrite")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "> auth-rewrite")
        assert_session_visible(screen, "auth-rewrite")

    def test_escape_clears_prepopulated_query(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="auth")
        time.sleep(0.5)
        ctrl.send_keys("Escape")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_search_bar_count(screen, 4, 4)


class TestQueryNoMatch:

    def test_nonmatching_query_shows_empty(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="zzz-no-match")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_empty_state(screen)


class TestQueryEdgeCases:

    def test_tag_syntax_in_query(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="'#sprint42'")
        time.sleep(1.0)
        screen = ctrl.capture()
        assert_session_visible(screen, "tagged-session")
        assert_search_bar_count(screen, 1, 1)

    def test_multi_word_query(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="fix login")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_session_visible(screen, "fix-login-bug")
