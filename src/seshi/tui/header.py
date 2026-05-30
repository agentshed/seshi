from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text


class Header(Widget):
    DEFAULT_CSS = """
    Header {
        height: 5;
        padding: 0 2;
    }
    """

    session_count: reactive[int] = reactive(0)
    shown_count: reactive[int] = reactive(0)
    indexing: reactive[bool] = reactive(False)

    accent: reactive[str] = reactive("#E08A5E")

    def watch_indexing(self, value: bool) -> None:
        self.refresh()

    def render(self) -> Text:
        from seshi import __version__
        text = Text()
        text.append("  █▀▀ █▀▀ █▀▀ █ █ ▀█▀", style=f"bold {self.accent}")
        text.append("   Seshi", style="bold")
        text.append(f"   {self.shown_count} of {self.session_count} sessions", style="dim")
        text.append(f"  v{__version__}", style="dim")
        if self.indexing:
            text.append("  indexing…", style="dim italic")
        text.append("\n")
        text.append("  ▀▀█ █▀▀ ▀▀█ █▀█  █ ", style=f"bold {self.accent}")
        text.append("   global session resumer", style="dim")
        text.append("\n")
        text.append("  ▀▀▀ ▀▀▀ ▀▀▀ ▀ ▀ ▀▀▀", style=f"bold {self.accent}")
        return text
