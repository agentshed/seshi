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

    accent: reactive[str] = reactive("#E08A5E")

    def render(self) -> Text:
        from seshi import __version__
        text = Text()
        text.append(" SESHI", style=f"bold {self.accent}")
        text.append(f"  {self.shown_count} of {self.session_count} sessions", style="dim")
        if self.sort_mode:
            text.append(f"  {self.sort_mode}", style="dim italic")
        if self.indexing:
            text.append("  indexing…", style="dim")
        text.append(f"  v{__version__}", style="dim")
        return text
