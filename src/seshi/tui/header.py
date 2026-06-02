from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text


class Header(Widget):
    DEFAULT_CSS = """
    Header {
        height: 1;
        padding: 0 1;
    }
    """

    session_count: reactive[int] = reactive(0)
    shown_count: reactive[int] = reactive(0)
    indexing: reactive[bool] = reactive(False)
    sort_mode: reactive[str] = reactive("")
    live_count: reactive[int] = reactive(0)

    accent: reactive[str] = reactive("#E08A5E")

    def watch_indexing(self, value: bool) -> None:
        self.refresh()

    def watch_live_count(self, value: int) -> None:
        self.refresh()

    def render(self) -> Text:
        from seshi import __version__
        text = Text()
        text.append(" SESHI", style=f"bold {self.accent}")
        text.append(f" {__version__}", style="dim")
        text.append(f"  {self.shown_count} of {self.session_count} sessions", style="dim")
        if self.live_count > 0:
            text.append(f"  {self.live_count} live", style=f"bold {self.accent}")
        if self.sort_mode:
            text.append(f"  sort by: {self.sort_mode}", style="dim italic")
        if self.indexing:
            text.append("  indexing…", style="dim")
        return text
