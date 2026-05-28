from textual.widget import Widget
from textual.message import Message
from textual.reactive import reactive
from textual import events
from rich.text import Text

from seshi.tui.blink import BlinkCursorMixin


class SearchBar(BlinkCursorMixin, Widget):
    DEFAULT_CSS = """
    SearchBar {
        height: 1;
        padding: 0 1;
    }
    """

    search_text: reactive[str] = reactive("")
    shown: reactive[int] = reactive(0)
    total: reactive[int] = reactive(0)
    sort_mode: reactive[str] = reactive("frecency")
    active: reactive[bool] = reactive(False)

    accent: reactive[str] = reactive("#E08A5E")
    can_focus = True

    def watch_active(self, active: bool) -> None:
        if active:
            self._start_blink()
        else:
            self._stop_blink()
            self._cursor_visible = False
        self.refresh()

    def render(self) -> Text:
        text = Text()
        text.append("  > ", style=f"bold {self.accent}")
        text.append(self.search_text, style="bold")
        if self.active and self._cursor_visible:
            text.append("_", style=f"bold {self.accent}")
        elif self.active:
            text.append(" ")
        text.append(f"  {self.sort_mode}", style="dim italic")
        padding = " " * max(1, 60 - len(self.search_text) - len(self.sort_mode))
        text.append(padding)
        text.append(f"{self.shown} / {self.total}", style="dim")
        return text

    def on_key(self, event: events.Key) -> None:
        if event.key == "backspace":
            if self.search_text:
                self.search_text = self.search_text[:-1]
                self.post_message(SearchChanged(self.search_text))
            event.stop()
        elif event.key == "escape":
            if self.search_text:
                self.search_text = ""
                self.post_message(SearchChanged(self.search_text))
                event.stop()
        elif event.key in ("up", "down", "enter"):
            sl = getattr(self.app, "_sessions_list", None)
            if sl:
                if event.key == "up":
                    sl.cursor = max(0, sl.cursor - 1)
                    sl.refresh()
                elif event.key == "down":
                    sl.cursor = min(len(sl.sessions) - 1, sl.cursor + 1)
                    sl.refresh()
                elif event.key == "enter":
                    s = sl.current_session
                    if s:
                        self.app.chosen_session = s
                        self.app.exit()
                        return
            event.stop()
        elif event.is_printable and event.character:
            self.search_text += event.character
            self.post_message(SearchChanged(self.search_text))
            event.stop()

    def parse_query(self) -> tuple[str, list[str]]:
        parts = self.search_text.split()
        tags = [p[1:] for p in parts if p.startswith("#")]
        text = " ".join(p for p in parts if not p.startswith("#"))
        return text, tags


class SearchChanged(Message):
    def __init__(self, query: str) -> None:
        self.query = query
        super().__init__()
