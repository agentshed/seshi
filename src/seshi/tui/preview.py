from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text

from seshi.models import Session
from seshi.transcript import find_transcript_path, extract_messages


class Preview(Widget):
    DEFAULT_CSS = """
    Preview {
        height: 8;
        padding: 0 1;
    }
    """

    session: reactive[Session | None] = reactive(None)

    def watch_session(self, session: Session | None) -> None:
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
        display = messages[-6:] if len(messages) > 6 else messages
        for msg in display:
            role_map = {"user": "you", "assistant": "asst", "system": "sys", "tool": "tool"}
            role_label = role_map.get(msg.role, msg.role)
            role_style = "#E08A5E" if msg.role == "user" else "#6BAED6"
            text.append(f"  ▎ {role_label:<5}", style=role_style)
            text.append(f" {msg.text[:120]}\n", style="dim")

        return text
