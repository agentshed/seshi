from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text

from seshi.models import Session
from seshi.transcript import find_transcript_path, extract_messages


class Preview(Widget):
    DEFAULT_CSS = """
    Preview {
        height: 1fr;
        padding: 0 1;
    }
    """

    session: reactive[Session | None] = reactive(None)
    focus_prompt_index: reactive[int | None] = reactive(None)
    highlight_query: reactive[str] = reactive("")

    def watch_session(self, session: Session | None) -> None:
        self.refresh()

    def watch_focus_prompt_index(self, index: int | None) -> None:
        self.refresh()

    def watch_highlight_query(self, query: str) -> None:
        self.refresh()

    def render(self) -> Text:
        text = Text()
        if not self.session:
            text.append("  no session selected", style="dim")
            return text

        s = self.session
        text.append(f"  {s.cwd}", style="dim")
        text.append(f"    {s.message_count} msgs    {s.token_count} tok\n", style="dim")

        path = find_transcript_path(s.session_id)
        if not path:
            text.append("  (no transcript on disk)", style="dim")
            return text

        messages = extract_messages(path)
        available_lines = max(self.size.height - 2, 4) if self.size.height > 0 else 6
        max_text_width = max(self.size.width - 12, 40) if self.size.width > 0 else 120

        if self.focus_prompt_index is not None and messages:
            user_count = 0
            focus_pos = None
            for i, msg in enumerate(messages):
                if msg.role == "user":
                    if user_count == self.focus_prompt_index:
                        focus_pos = i
                        break
                    user_count += 1
            if focus_pos is not None:
                half = available_lines // 2
                start = max(0, focus_pos - half)
                end = min(len(messages), start + available_lines)
                if end - start < available_lines:
                    start = max(0, end - available_lines)
                display = messages[start:end]
            else:
                display = messages[-available_lines:] if len(messages) > available_lines else messages
        else:
            display = messages[-available_lines:] if len(messages) > available_lines else messages

        for msg in display:
            role_map = {"user": "you", "assistant": "asst", "system": "sys", "tool": "tool"}
            role_label = role_map.get(msg.role, msg.role)
            role_style = "#E08A5E" if msg.role == "user" else "#6BAED6"

            line = Text()
            line.append(f"  ▎ {role_label:<5}", style=role_style)
            line.append(f" {msg.text[:max_text_width]}\n", style="dim")

            if self.highlight_query:
                line.highlight_words([self.highlight_query], style="bold underline", case_sensitive=False)

            text.append_text(line)

        return text
