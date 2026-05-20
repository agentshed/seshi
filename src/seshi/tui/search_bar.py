from textual.widget import Widget
from textual.message import Message
from textual.reactive import reactive
from textual import events
from rich.text import Text


class SearchBar(Widget):
    DEFAULT_CSS = """
    SearchBar {
        height: 1;
        padding: 0 1;
    }
    """

    query: reactive[str] = reactive("")
    shown: reactive[int] = reactive(0)
    total: reactive[int] = reactive(0)
    sort_mode: reactive[str] = reactive("frecency")

    accent: reactive[str] = reactive("#E08A5E")
    can_focus = True

    def render(self) -> Text:
        text = Text()
        text.append("  > ", style=f"bold {self.accent}")
        text.append(self.query, style="bold")
        text.append("▮", style="dim")
        text.append(f"  {self.sort_mode}", style="dim italic")
        padding = " " * max(1, 60 - len(self.query) - len(self.sort_mode))
        text.append(padding)
        text.append(f"{self.shown} / {self.total}", style="dim")
        return text

    def on_key(self, event: events.Key) -> None:
        if event.key == "backspace":
            if self.query:
                self.query = self.query[:-1]
                self.post_message(SearchChanged(self.query))
            event.stop()
        elif event.key == "escape":
            if self.query:
                self.query = ""
                self.post_message(SearchChanged(self.query))
                event.stop()
        elif event.is_printable and event.character:
            self.query += event.character
            self.post_message(SearchChanged(self.query))
            event.stop()

    def parse_query(self) -> tuple[str, list[str]]:
        parts = self.query.split()
        tags = [p[1:] for p in parts if p.startswith("#")]
        text = " ".join(p for p in parts if not p.startswith("#"))
        return text, tags


class SearchChanged(Message):
    def __init__(self, query: str) -> None:
        self.query = query
        super().__init__()
