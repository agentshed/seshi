"""TUI integration tests: `seshi <query>` opens TUI with pre-populated search."""

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
        screen = ctrl.wait_for("> auth")
        assert_session_visible(screen, "auth-rewrite")

    def test_query_filters_results(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="auth")
        screen = ctrl.wait_for("1 / 4")
        assert_screen_contains(screen, "> auth")

    def test_user_can_refine_query(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="auth")
        ctrl.wait_for("> auth")
        ctrl.send_text("-rewrite")
        screen = ctrl.wait_for("> auth-rewrite")
        assert_session_visible(screen, "auth-rewrite")

    def test_escape_clears_prepopulated_query(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="auth")
        ctrl.wait_for("> auth")
        ctrl.send_keys("Escape")
        screen = ctrl.wait_for("4 / 4")


class TestQueryNoMatch:

    def test_nonmatching_query_shows_empty(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="zzz-no-match")
        screen = ctrl.wait_for("0 / ")
        assert_empty_state(screen)


class TestQueryEdgeCases:

    def test_tag_syntax_in_query(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="'#sprint42'")
        screen = ctrl.wait_for("tagged-session")
        assert_search_bar_count(screen, 1, 1)

    def test_multi_word_query(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_search, extra_args="fix login")
        screen = ctrl.wait_for("fix-login-bug")
