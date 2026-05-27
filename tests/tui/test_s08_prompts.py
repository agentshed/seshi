import pytest
import time

from tests.tui.assertions import (
    assert_screen_contains,
    assert_screen_not_contains,
    assert_session_visible,
    assert_search_bar_count,
)
from tests.tui.seed import seed_with_prompts, seed_for_bulk, insert_prompts


@pytest.mark.smoke
class TestPromptDisplay:

    def test_prompts_visible_by_default(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "│")
        assert_screen_contains(screen, "fix the auth bug")

    def test_session_header_shows_collapse_indicator(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "▾")

    def test_prompt_row_shows_text(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "deploy to staging")

    def test_session_with_no_prompts_no_expand_indicator(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        ctrl.send_keys("G")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_session_visible(screen, "no-prompts")
        line = screen.line_containing("no-prompts")
        assert line is not None
        assert "▾" not in line and "▸" not in line


@pytest.mark.smoke
class TestPromptNavigation:

    def test_j_navigates_through_prompt_rows(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        ctrl.send_keys("j")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_screen_contains(screen, "│")

    def test_g_jumps_to_first_row(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        for _ in range(5):
            ctrl.send_keys("j")
        time.sleep(0.3)
        ctrl.send_keys("g")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_session_visible(screen, "multi-prompt")


class TestExpandCollapse:

    def test_e_collapses_session(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        time.sleep(0.3)
        ctrl.send_keys("e")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_screen_contains(screen, "▸")

    def test_e_expands_collapsed_session(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        time.sleep(0.3)
        ctrl.send_keys("e")
        time.sleep(0.3)
        ctrl.send_keys("e")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_screen_contains(screen, "▾")

    def test_E_collapses_all(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        time.sleep(0.3)
        ctrl.send_keys("E")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_not_contains(screen, "fix the auth bug")

    def test_E_expands_all(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        time.sleep(0.3)
        ctrl.send_keys("E")
        time.sleep(0.3)
        ctrl.send_keys("E")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "fix the auth bug")


class TestActionsOnPromptRows:

    def test_favorite_on_prompt_row(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        ctrl.send_keys("j")
        time.sleep(0.3)
        ctrl.send_keys("f")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "★ favorites")

    def test_space_on_prompt_row_selects_session(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        ctrl.send_keys("j")
        time.sleep(0.3)
        ctrl.send_keys("space")
        time.sleep(0.3)
        screen = ctrl.capture()
        assert_screen_contains(screen, "[x]")


class TestPromptSearch:

    def test_search_matches_prompt_text(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("middleware")
        time.sleep(1.0)
        screen = ctrl.capture()
        assert_session_visible(screen, "multi-prompt")
        assert_screen_contains(screen, "middleware")

    def test_search_auto_expands_matching_session(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        ctrl.send_keys("E")
        time.sleep(0.3)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("middleware")
        time.sleep(1.0)
        screen = ctrl.capture()
        assert_screen_contains(screen, "│")

    def test_clear_search_restores_full_list(self, tui_custom):
        ctrl, sessions = tui_custom(seed_with_prompts)
        ctrl.send_keys("/")
        time.sleep(0.3)
        ctrl.send_text("middleware")
        time.sleep(0.5)
        ctrl.send_keys("Escape")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_session_visible(screen, "multi-prompt")
        assert_session_visible(screen, "many-prompts")
