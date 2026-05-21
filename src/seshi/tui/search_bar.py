from textual.widget import Widget
from textual.message import Message
from textual.reactive import reactive
from textual import events
from textual.timer import Timer
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
    active: reactive[bool] = reactive(False)

    accent: reactive[str] = reactive("#E08A5E")
    can_focus = True

    _cursor_visible: bool = True
    _blink_timer: Timer | None = None

    def watch_active(self, active: bool) -> None:
        if active:
            self._cursor_visible = True
            self._blink_timer = self.set_interval(0.5, self._toggle_cursor)
        else:
            if self._blink_timer:
                self._blink_timer.stop()
                self._blink_timer = None
            self._cursor_visible = False
        self.refresh()

    def _toggle_cursor(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.refresh()

    def render(self) -> Text:
        text = Text()
        text.append("  > ", style=f"bold {self.accent}")
        text.append(self.query, style="bold")
        if self.active and self._cursor_visible:
            text.append("▮", style=f"bold {self.accent}")
        elif self.active:
            text.append(" ")
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
