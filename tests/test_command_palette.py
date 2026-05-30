"""Tests for the command palette (Item 13)."""
from seshi.tui.commands import SeshiCommands
from seshi.tui.app import SeshiApp


def test_command_provider_class_exists():
    assert SeshiCommands is not None


def test_app_has_commands_configured():
    assert SeshiCommands in SeshiApp.COMMANDS


def test_app_has_action_methods():
    action_names = [
        "action_resume", "action_rename", "action_favorite",
        "action_tag", "action_archive", "action_delete",
        "action_cycle_sort", "action_toggle_preview",
        "action_toggle_expand", "action_toggle_expand_all",
        "action_undo", "action_toggle_hide_missing",
        "action_toggle_hide_stale",
        "action_view_sessions", "action_view_overview",
        "action_view_projects", "action_view_help",
    ]
    for name in action_names:
        assert hasattr(SeshiApp, name), f"SeshiApp missing {name}"


def test_help_text_mentions_command_palette():
    from seshi.tui.help_view import HELP_TEXT
    assert "Ctrl-p" in HELP_TEXT
    assert "command palette" in HELP_TEXT.lower()


def test_help_text_mentions_undo():
    from seshi.tui.help_view import HELP_TEXT
    assert "z" in HELP_TEXT
    assert "undo" in HELP_TEXT.lower()
