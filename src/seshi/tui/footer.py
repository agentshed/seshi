from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text


class Footer(Widget):
    DEFAULT_CSS = """
    Footer {
        height: 1;
        dock: bottom;
    }
    """

    view: reactive[str] = reactive("sessions")
    has_selection: reactive[bool] = reactive(False)
    mode: reactive[str] = reactive("normal")
    accent: reactive[str] = reactive("#E08A5E")

    def render(self) -> Text:
        text = Text()
        if self.mode == "rename":
            text.append("  Enter", style=f"bold {self.accent}")
            text.append(" save   ", style="dim")
            text.append("Esc", style=f"bold {self.accent}")
            text.append(" cancel", style="dim")
            return text

        if self.mode == "tag":
            text.append("  Enter", style=f"bold {self.accent}")
            text.append(" apply   ", style="dim")
            text.append("Esc", style=f"bold {self.accent}")
            text.append(" cancel", style="dim")
            return text

        if self.view == "sessions":
            keys = [
                ("↵", "resume"), ("r", "rename"), ("f", "favorite"),
                ("t", "tag"), ("u", "archive"), ("d", "delete"),
                ("s", "sort"), ("Space", "select"), ("Tab", "view"),
            ]
        elif self.view == "projects":
            keys = [
                ("↵", "open"), ("f", "favorite"), ("r", "rename"), ("Tab", "view"),
            ]
        else:
            keys = [("Tab", "view")]

        for key, label in keys:
            text.append(f"  {key}", style=f"bold {self.accent}")
            text.append(f" {label}", style="dim")

        return text
