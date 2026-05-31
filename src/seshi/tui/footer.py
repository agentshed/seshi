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
    preview_visible: reactive[bool] = reactive(True)

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
                ("↵", "resume"), ("/", "search"), ("f", "fav"),
                ("d", "delete"), ("z", "undo"), ("s", "sort"),
                ("r", "rename"), ("t", "tag"), ("P", "project"),
                ("u", "archive"), ("e", "expand"), ("c", "compact"),
                ("H", "hide"),
                ("p", "preview" if self.preview_visible else "hidden"),
                ("Space", "select"), ("?", "help"),
            ]
        elif self.view == "projects":
            keys = [
                ("↵", "open"), ("f", "favorite"), ("r", "rename"),
                ("g/G", "top/end"), ("Tab", "view"),
            ]
        elif self.view == "overview":
            keys = [("j/k", "scroll"), ("Tab", "view")]
        else:
            keys = [("j/k", "scroll"), ("Tab", "view")]

        try:
            w = self.size.width if self.size.width > 0 else 200
        except (ValueError, AttributeError):
            w = 200
        more_len = len("  ? more")
        for i, (key, label) in enumerate(keys):
            entry = f"  {key} {label}"
            remaining = keys[i + 1:]
            if remaining and len(text.plain) + len(entry) + more_len > w:
                text.append("  ?", style=f"bold {self.accent}")
                text.append(" more", style="dim")
                break
            if len(text.plain) + len(entry) > w:
                break
            text.append(f"  {key}", style=f"bold {self.accent}")
            text.append(f" {label}", style="dim")

        return text
