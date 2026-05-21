from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static
from textual import events


class ConfirmBulkScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmBulkScreen {
        align: center middle;
    }
    #confirm-dialog {
        width: 50;
        height: 7;
        border: solid;
        padding: 1 2;
        background: $surface;
    }
    """

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._message = message

    def compose(self) -> ComposeResult:
        yield Static(
            f"{self._message}\n\n  [bold]y[/bold] confirm    [bold]n / Esc[/bold] cancel",
            id="confirm-dialog",
        )

    def on_key(self, event: events.Key) -> None:
        if event.key in ("y", "Y"):
            self.dismiss(True)
        elif event.key in ("n", "N", "escape"):
            self.dismiss(False)
        event.stop()
