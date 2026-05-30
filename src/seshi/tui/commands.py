from __future__ import annotations

from functools import partial

from textual.command import Provider, Hit, Hits


class SeshiCommands(Provider):

    async def search(self, query: str) -> Hits:
        commands = [
            ("Resume session", "Resume the selected session", "action_resume"),
            ("Rename session", "Rename the selected session inline", "action_rename"),
            ("Toggle favorite", "Toggle favorite on the selected session", "action_favorite"),
            ("Toggle tag", "Add or remove a tag on the selected session", "action_tag"),
            ("Toggle archive", "Archive or unarchive the selected session", "action_archive"),
            ("Delete session", "Delete the selected session (with confirmation)", "action_delete"),
            ("Cycle sort mode", "Cycle between frecency, recency, and frequency", "action_cycle_sort"),
            ("Toggle preview pane", "Show or hide the preview pane", "action_toggle_preview"),
            ("Toggle expand", "Expand or collapse current session prompts", "action_toggle_expand"),
            ("Expand/collapse all", "Toggle expand on all sessions", "action_toggle_expand_all"),
            ("Undo last action", "Undo the most recent mutation", "action_undo"),
            ("Toggle hide missing dirs", "Hide sessions with missing directories", "action_toggle_hide_missing"),
            ("Toggle hide stale sessions", "Hide stale sessions not in Claude Code", "action_toggle_hide_stale"),
            ("View: Sessions", "Switch to sessions view", "action_view_sessions"),
            ("View: Overview", "Switch to overview", "action_view_overview"),
            ("View: Projects", "Switch to projects view", "action_view_projects"),
            ("View: Help", "Switch to help view", "action_view_help"),
        ]

        matcher = self.matcher(query)
        for title, description, callback_name in commands:
            score = matcher.match(title)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(title),
                    partial(self._run_command, callback_name),
                    help=description,
                )

    async def _run_command(self, action_name: str) -> None:
        self.app.call_later(getattr(self.app, action_name))
