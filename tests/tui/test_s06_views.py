import pytest
import time

from tests.tui.assertions import (
    assert_screen_contains,
    assert_screen_not_contains,
    assert_view_active,
    assert_footer_shows,
    assert_header_visible,
    assert_empty_state,
    assert_session_visible,
)
from tests.tui.seed import seed_for_projects, seed_for_actions, insert_session


class TestViewSwitching:

    def test_tab_cycles_forward(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("Tab")
        time.sleep(0.5)
        assert_view_active(ctrl.capture(), "overview")
        ctrl.send_keys("Tab")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "sessions")  # projects show "N sessions"
        ctrl.send_keys("Tab")
        time.sleep(0.5)
        assert_view_active(ctrl.capture(), "help")
        ctrl.send_keys("Tab")
        time.sleep(0.5)
        assert_header_visible(ctrl.capture())

    def test_shift_tab_cycles_backward(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("BTab")
        time.sleep(0.5)
        assert_view_active(ctrl.capture(), "help")

    def test_number_keys_switch_views(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("2")
        time.sleep(0.5)
        assert_view_active(ctrl.capture(), "overview")
        ctrl.send_keys("1")
        time.sleep(0.5)
        assert_header_visible(ctrl.capture())
        ctrl.send_keys("3")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_footer_shows(screen, "open")

    def test_question_mark_shows_help(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("?")
        time.sleep(0.5)
        assert_view_active(ctrl.capture(), "help")

    def test_escape_from_other_view_returns_to_sessions(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("2")
        time.sleep(0.5)
        assert_view_active(ctrl.capture(), "overview")
        ctrl.send_keys("Escape")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_footer_shows(screen, "resume")


class TestOverviewView:

    def test_overview_shows_totals(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("2")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "Totals")
        assert_screen_contains(screen, "sessions:")

    def test_overview_shows_sparkline(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("2")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "Last 30 days")

    def test_overview_shows_span(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("2")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "Span")


class TestProjectsView:

    def test_projects_list(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_projects)
        ctrl.send_keys("3")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "project-alpha")
        assert_screen_contains(screen, "project-beta")

    def test_project_drill_down(self, tui_custom):
        ctrl, _ = tui_custom(seed_for_projects)
        ctrl.send_keys("3")
        time.sleep(0.5)
        ctrl.send_keys("Enter")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_footer_shows(screen, "resume")
        assert_screen_contains(screen, "project-alpha")

    def test_project_favorite(self, tui_custom, db_path):
        ctrl, _ = tui_custom(seed_for_projects)
        ctrl.send_keys("3")
        time.sleep(0.5)
        ctrl.send_keys("f")
        time.sleep(0.5)
        from tests.tui.tmux_controller import TmuxController
        rows = TmuxController.query_db(
            db_path,
            "SELECT COUNT(*) as cnt FROM project_favorites",
        )
        assert rows[0]["cnt"] == 1

    def test_projects_empty(self, tui_empty):
        ctrl = tui_empty
        ctrl.send_keys("3")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "No projects found")


class TestHelpView:

    def test_help_shows_navigation(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("?")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "Navigation")
        assert_screen_contains(screen, "Move cursor")

    def test_help_shows_actions(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("?")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_screen_contains(screen, "Actions")
        assert_screen_contains(screen, "Rename session")

    def test_help_footer_minimal(self, tui):
        ctrl, _ = tui
        ctrl.send_keys("?")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_footer_shows(screen, "view")
        assert_screen_not_contains(screen, "delete")
