from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.tui.tmux_controller import CapturedScreen


def assert_screen_contains(screen: CapturedScreen, text: str, msg: str = "") -> None:
    if text not in screen:
        detail = msg or f"Expected screen to contain '{text}'"
        raise AssertionError(f"{detail}\n\nScreen content:\n{screen.raw}")


def assert_screen_not_contains(screen: CapturedScreen, text: str, msg: str = "") -> None:
    if text in screen:
        detail = msg or f"Expected screen to NOT contain '{text}'"
        raise AssertionError(f"{detail}\n\nScreen content:\n{screen.raw}")


def assert_header_visible(screen: CapturedScreen) -> None:
    assert_screen_contains(screen, "█▀▀ █▀▀ █▀▀", "Header ASCII art not visible")
    assert_screen_contains(screen, "Seshi", "Header 'Seshi' text not visible")


def assert_session_count(screen: CapturedScreen, shown: int, total: int) -> None:
    expected = f"{shown} of {total} sessions"
    assert_screen_contains(screen, expected, f"Expected header to show '{expected}'")


def assert_search_bar_count(screen: CapturedScreen, shown: int, total: int) -> None:
    expected = f"{shown} / {total}"
    assert_screen_contains(screen, expected, f"Expected search bar to show '{expected}'")


def assert_sort_mode(screen: CapturedScreen, mode: str) -> None:
    assert_screen_contains(screen, mode, f"Expected sort mode '{mode}' in search bar")


def assert_session_visible(screen: CapturedScreen, name: str) -> None:
    assert_screen_contains(screen, name, f"Session '{name}' not visible")


def assert_session_not_visible(screen: CapturedScreen, name: str) -> None:
    assert_screen_not_contains(screen, name, f"Session '{name}' should not be visible")


def assert_favorite_marker(screen: CapturedScreen, name: str) -> None:
    line = screen.line_containing(name)
    assert line is not None, f"Session '{name}' not found on screen"
    assert " * " in line, f"Expected favorite marker '*' in line: {line}"


def assert_no_favorite_marker(screen: CapturedScreen, name: str) -> None:
    line = screen.line_containing(name)
    assert line is not None, f"Session '{name}' not found on screen"
    assert " * " not in line, f"Unexpected favorite marker in line: {line}"


def assert_tag_visible(screen: CapturedScreen, tag: str) -> None:
    assert_screen_contains(screen, f"#{tag}", f"Tag '#{tag}' not visible")


def assert_selection_marker(screen: CapturedScreen, name: str) -> None:
    line = screen.line_containing(name)
    assert line is not None, f"Session '{name}' not found on screen"
    assert "[x]" in line, f"Expected selection marker '[x]' in line: {line}"


def assert_no_selection_marker(screen: CapturedScreen, name: str) -> None:
    line = screen.line_containing(name)
    assert line is not None, f"Session '{name}' not found on screen"
    assert "[x]" not in line, f"Unexpected selection marker in line: {line}"


def assert_input_prompt(screen: CapturedScreen, mode: str) -> None:
    assert_screen_contains(screen, f"{mode}:", f"Expected '{mode}:' input prompt")


def assert_no_input_prompt(screen: CapturedScreen) -> None:
    assert_screen_not_contains(screen, "rename:", "Unexpected rename prompt")
    assert_screen_not_contains(screen, "tag:", "Unexpected tag prompt")


def assert_view_active(screen: CapturedScreen, view: str) -> None:
    markers = {
        "overview": "Totals",
        "help": "Navigation",
    }
    marker = markers.get(view)
    if marker:
        assert_screen_contains(screen, marker, f"Expected {view} view to be active")


def assert_footer_shows(screen: CapturedScreen, key: str) -> None:
    assert_screen_contains(screen, key, f"Expected footer to show '{key}'")


def assert_empty_state(screen: CapturedScreen) -> None:
    assert_screen_contains(screen, "no sessions found", "Expected 'no sessions found' message")
