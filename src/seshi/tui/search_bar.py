from textual.widget import Widget
from textual.message import Message
from textual.reactive import reactive
from textual import events
from textual.timer import Timer
from rich.text import Text

SCOPES = ["all", "favorites", "recent", "project"]


class SearchBar(Widget):
    DEFAULT_CSS = """
    SearchBar {
        height: 1;
        padding: 0 1;
    }
    """

    search_text: reactive[str] = reactive("")
    shown: reactive[int] = reactive(0)
    total: reactive[int] = reactive(0)
    active: reactive[bool] = reactive(False)
    scope: reactive[str] = reactive("all")
    mode: reactive[str] = reactive("search")

    accent: reactive[str] = reactive("#E08A5E")
    can_focus = True

    _cursor_visible: bool = True
    _blink_timer: Timer | None = None
    _has_filter_cwd: bool = False
    _saved_search_text: str = ""
    _saved_scope: str = "all"

    def enter_mode(self, mode: str, prefill: str = "") -> None:
        self._saved_search_text = self.search_text
        self._saved_scope = self.scope
        self.mode = mode
        self.search_text = prefill
        self.active = True
        try:
            self.focus()
        except Exception:
            pass

    def exit_mode(self) -> None:
        if self.mode == "search":
            return
        self.mode = "search"
        self.search_text = self._saved_search_text
        self.scope = self._saved_scope
        self.active = False

    def watch_active(self, active: bool) -> None:
        if active:
            self._cursor_visible = True
            try:
                self._blink_timer = self.set_interval(0.5, self._toggle_cursor)
            except RuntimeError:
                pass
        else:
            if self._blink_timer:
                self._blink_timer.stop()
                self._blink_timer = None
            self._cursor_visible = False
        self.refresh()

    def _toggle_cursor(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.refresh()

    def _cycle_scope(self) -> None:
        idx = SCOPES.index(self.scope) if self.scope in SCOPES else 0
        for _ in range(len(SCOPES)):
            idx = (idx + 1) % len(SCOPES)
            candidate = SCOPES[idx]
            if candidate == "project" and not self._has_filter_cwd:
                continue
            self.scope = candidate
            return
        self.scope = "all"

    def render(self) -> Text:
        text = Text()
        text.append(f"  {self.mode}> ", style=f"bold {self.accent}")
        text.append(self.search_text, style="bold")
        if self.active and self._cursor_visible:
            text.append("_", style=f"bold {self.accent}")
        elif self.active:
            text.append(" ")
        if self.mode == "search":
            if self.scope != "all":
                text.append(f"  [{self.scope}]", style=f"bold {self.accent}")
            count_str = f"{self.shown} / {self.total}"
            used = len(text)
            padding = " " * max(1, 70 - used - len(count_str))
            text.append(padding)
            text.append(count_str, style="dim")
        return text

    def on_key(self, event: events.Key) -> None:
        if event.key == "backspace":
            if self.search_text:
                self.search_text = self.search_text[:-1]
                if self.mode == "search":
                    self.post_message(SearchChanged(self.search_text, self.scope))
            self.refresh()
            event.stop()
        elif event.key == "escape":
            if self.mode != "search":
                mode = self.mode
                self.exit_mode()
                self.post_message(InputCancelled(mode))
                event.stop()
            elif self.search_text or self.scope != "all":
                self.search_text = ""
                self.scope = "all"
                self.post_message(SearchChanged(self.search_text, self.scope))
                event.stop()
        elif event.key == "ctrl+o":
            if self.mode == "search":
                self._cycle_scope()
                self.post_message(SearchChanged(self.search_text, self.scope))
            event.stop()
        elif event.key in ("up", "down", "enter"):
            if self.mode != "search":
                if event.key == "enter":
                    mode = self.mode
                    submitted_text = self.search_text
                    self.exit_mode()
                    self.post_message(InputSubmitted(mode, submitted_text))
                event.stop()
                return
            sl = getattr(self.app, "_sessions_list", None)
            if sl:
                if event.key == "up":
                    sl.cursor = max(0, sl.cursor - 1)
                    sl.refresh()
                elif event.key == "down":
                    sl.cursor = min(sl._nav_row_count() - 1, sl.cursor + 1)
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
            if self.mode == "search":
                self.post_message(SearchChanged(self.search_text, self.scope))
            self.refresh()
            event.stop()

    def parse_query(self) -> tuple[str, list[str]]:
        parts = self.search_text.split()
        tags = [p[1:] for p in parts if p.startswith("#")]
        text = " ".join(p for p in parts if not p.startswith("#"))
        return text, tags


class SearchChanged(Message):
    def __init__(self, query: str, scope: str = "all") -> None:
        self.query = query
        self.scope = scope
        super().__init__()


class InputSubmitted(Message):
    def __init__(self, mode: str, text: str) -> None:
        self.mode = mode
        self.text = text
        super().__init__()


class InputCancelled(Message):
    def __init__(self, mode: str) -> None:
        self.mode = mode
        super().__init__()
