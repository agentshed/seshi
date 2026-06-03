from pathlib import Path

from textual.widget import Widget
from textual.reactive import reactive
from textual import events
from rich.text import Text

from seshi.models import Session
from seshi.live import LiveInfo
from seshi.transcript import find_transcript_path, extract_messages


class Preview(Widget):
    DEFAULT_CSS = """
    Preview {
        height: 1fr;
        padding: 0 1;
    }
    """

    can_focus = True

    session: reactive[Session | None] = reactive(None)
    focus_prompt_index: reactive[int | None] = reactive(None)
    highlight_query: reactive[str] = reactive("")
    user_color: reactive[str] = reactive("#E08A5E")
    assistant_color: reactive[str] = reactive("#6BAED6")
    live_state: reactive[LiveInfo | None] = reactive(None)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cached_session_id: str | None = None
        self._cached_messages: list = []
        self._scroll_offset: int = 0
        self._live_messages: list = []

    def watch_session(self, session: Session | None) -> None:
        self._update_cache(session)
        if session and not self._cached_messages:
            path = find_transcript_path(session.session_id)
            if path:
                self._cached_session_id = None
                self._update_cache(session)
        if not self.has_focus:
            self._scroll_offset = 0
        self.refresh()

    def watch_focus_prompt_index(self, index: int | None) -> None:
        if not self.has_focus:
            self._scroll_offset = 0
        self.refresh()

    def watch_highlight_query(self, query: str) -> None:
        self.refresh()

    def watch_live_state(self, state: LiveInfo | None) -> None:
        if state is not None:
            self._refresh_live_transcript()
            self._scroll_offset = 0
        else:
            if self._live_messages:
                self._scroll_offset = 0
            self._live_messages = []
        self.refresh()

    def _refresh_live_transcript(self) -> None:
        if self.live_state is None or not self.session:
            self._live_messages = []
            return
        tp = self.live_state.transcript_path
        if tp:
            self._live_messages = extract_messages(Path(tp))
        else:
            path = find_transcript_path(self.session.session_id)
            if path:
                self._live_messages = extract_messages(path)
            else:
                self._live_messages = []

    def _update_cache(self, session: Session | None) -> None:
        if session is None:
            self._cached_session_id = None
            self._cached_messages = []
            return
        if session.session_id == self._cached_session_id:
            return
        self._cached_session_id = session.session_id
        path = find_transcript_path(session.session_id)
        if path:
            self._cached_messages = extract_messages(path)
        else:
            self._cached_messages = []

    def _available_lines(self) -> int:
        return max(self.size.height - 2, 4) if self.size.height > 0 else 6

    def on_focus(self, event: events.Focus) -> None:
        self._sync_scroll_to_focus()
        self.refresh()

    def on_blur(self, event: events.Blur) -> None:
        self._scroll_offset = 0
        self.refresh()

    @staticmethod
    def _compute_start_offset(messages: list, focus_prompt_index: int | None, available: int) -> int:
        """Compute the start offset for centering on a focused prompt."""
        if not messages:
            return 0
        if focus_prompt_index is not None:
            user_count = 0
            focus_pos = None
            for i, msg in enumerate(messages):
                if msg.role == "user":
                    if user_count == focus_prompt_index:
                        focus_pos = i
                        break
                    user_count += 1
            if focus_pos is not None:
                half = available // 2
                start = max(0, focus_pos - half)
                end = min(len(messages), start + available)
                if end - start < available:
                    start = max(0, end - available)
                return start
        return max(0, len(messages) - available)

    def _sync_scroll_to_focus(self) -> None:
        """Set scroll offset to match the current auto-centered position."""
        self._scroll_offset = self._compute_start_offset(
            self._cached_messages, self.focus_prompt_index, self._available_lines()
        )

    def on_key(self, event: events.Key) -> None:
        if not self.has_focus:
            return
        messages = self._live_messages if self.live_state else self._cached_messages
        if not messages:
            return
        available = self._available_lines()
        max_offset = max(0, len(messages) - available)

        handled = True
        if event.key in ("j", "down"):
            self._scroll_offset = min(self._scroll_offset + 1, max_offset)
        elif event.key in ("k", "up"):
            self._scroll_offset = max(self._scroll_offset - 1, 0)
        elif event.key == "g":
            self._scroll_offset = 0
        elif event.key in ("G", "shift+g"):
            self._scroll_offset = max_offset
        elif event.key == "ctrl+d":
            page = max(1, available // 2)
            self._scroll_offset = min(self._scroll_offset + page, max_offset)
        elif event.key == "ctrl+u":
            page = max(1, available // 2)
            self._scroll_offset = max(self._scroll_offset - page, 0)
        else:
            handled = False

        if handled:
            event.prevent_default()
            event.stop()
            self.refresh()

    def _render_live(self) -> Text:
        text = Text()
        s = self.session
        live = self.live_state
        max_w = max(self.size.width - 6, 40) if self.size.width > 0 else 120
        total_lines = self._available_lines() + 2

        status_labels = {"busy": "Working", "needs_input": "Needs input", "idle": "Idle"}
        status_label = status_labels.get(live.status, live.status)
        status_colors = {"busy": self.user_color, "needs_input": "yellow", "idle": "dim"}
        status_color = status_colors.get(live.status, "dim")

        text.append("  ● ", style=status_color)
        text.append(status_label, style=f"bold {status_color}")
        if live.detail:
            text.append(f"  {live.detail}", style="dim")
        text.append("\n")

        tools = live.tools
        if tools:
            text.append("\n")
            for tc in tools:
                line = Text()
                line.append(f"  {tc.name:<6}", style=f"bold {self.assistant_color}")
                line.append(f" {tc.summary[:max_w]}\n", style="")
                text.append_text(line)

        header_lines = 2 + (len(tools) + 1 if tools else 0)

        sep_w = max(self.size.width - 4, 20) if self.size.width > 0 else 80
        text.append(f"\n  {'─' * sep_w}\n", style="dim")
        header_lines += 2

        messages = self._live_messages
        tail_lines = max(4, total_lines - header_lines)

        if not messages:
            text.append("  (waiting for transcript…)\n", style="dim")
            return text

        display = messages[-tail_lines:] if len(messages) > tail_lines else messages

        for msg in display:
            role_map = {"user": "you", "assistant": "asst", "system": "sys", "tool": "tool"}
            role_label = role_map.get(msg.role, msg.role)
            role_style = self.user_color if msg.role == "user" else self.assistant_color

            line = Text()
            line.append(f"  ▎ {role_label:<5}", style=role_style)
            line.append(f" {msg.text[:max_w]}\n", style="dim")
            text.append_text(line)

        return text

    def render(self) -> Text:
        text = Text()
        if not self.session:
            text.append("  no session selected", style="dim")
            return text

        if self.live_state is not None:
            return self._render_live()

        s = self.session

        header = Text()
        header.append(f"  {s.cwd}", style="dim")

        messages = self._cached_messages
        available_lines = self._available_lines()

        if self.has_focus and messages:
            total = len(messages)
            start = self._scroll_offset + 1
            end = min(self._scroll_offset + available_lines, total)
            header.append(f"  [{start}-{end}/{total}]", style="bold")
        else:
            header.append(f"    {s.message_count} msgs    {s.token_count} tok\n", style="dim")

        text.append_text(header)
        if self.has_focus and messages:
            text.append("\n")

        if not messages:
            text.append("  (no transcript on disk)", style="dim")
            return text

        max_text_width = max(self.size.width - 12, 40) if self.size.width > 0 else 120

        if self.has_focus and messages:
            start = self._scroll_offset
            end = min(start + available_lines, len(messages))
            display = messages[start:end]
        elif self.focus_prompt_index is not None and messages:
            start = self._compute_start_offset(messages, self.focus_prompt_index, available_lines)
            end = min(start + available_lines, len(messages))
            display = messages[start:end]
        else:
            display = messages[-available_lines:] if len(messages) > available_lines else messages

        for msg in display:
            role_map = {"user": "you", "assistant": "asst", "system": "sys", "tool": "tool"}
            role_label = role_map.get(msg.role, msg.role)
            role_style = self.user_color if msg.role == "user" else self.assistant_color

            line = Text()
            line.append(f"  ▎ {role_label:<5}", style=role_style)
            line.append(f" {msg.text[:max_text_width]}\n", style="dim")

            if self.highlight_query:
                line.highlight_words([self.highlight_query], style="bold underline", case_sensitive=False)

            text.append_text(line)

        return text
