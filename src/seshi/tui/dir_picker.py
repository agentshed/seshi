import os
import sqlite3

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static
from textual import events
from rich.text import Text

from seshi.lang_detect import detect_language
from seshi.time_utils import relative_time


class DirPickerScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
    ]
    DEFAULT_CSS = """
    DirPickerScreen {
        align: center middle;
    }
    #dir-picker-dialog {
        width: 80%;
        height: 80%;
        border: solid;
        padding: 1 2;
        background: $surface;
    }
    """

    def __init__(self, conn: sqlite3.Connection, **kwargs) -> None:
        super().__init__(**kwargs)
        self.conn = conn
        self._dirs: list[dict] = []
        self._cursor: int = 0
        self._sort_mode: str = "frecency"
        self._load_dirs()

    def _load_dirs(self) -> None:
        rows = self.conn.execute("""
            SELECT cwd,
                   COUNT(*) as count,
                   MAX(last_activity_at) as last_active,
                   SUM(frecency_rank) as total_frecency
            FROM sessions
            WHERE is_archived = 0
            GROUP BY cwd
        """).fetchall()

        self._dirs = []
        for r in rows:
            self._dirs.append({
                "cwd": r["cwd"],
                "count": r["count"],
                "last_active": r["last_active"],
                "total_frecency": r["total_frecency"] or 0,
            })

        self._apply_sort()

    def _apply_sort(self) -> None:
        if self._sort_mode == "frecency":
            self._dirs.sort(key=lambda d: -d["total_frecency"])
        elif self._sort_mode == "recency":
            self._dirs.sort(key=lambda d: -d["last_active"])
        elif self._sort_mode == "frequency":
            self._dirs.sort(key=lambda d: (-d["count"], -d["last_active"]))

    def compose(self) -> ComposeResult:
        yield Static("", id="dir-picker-dialog")

    def on_mount(self) -> None:
        self._refresh_content()

    def _refresh_content(self) -> None:
        dialog = self.query_one("#dir-picker-dialog", Static)
        dialog.update(self._render_content())

    def _render_content(self) -> Text:
        text = Text()

        text.append("  New session - choose directory", style="bold")
        text.append(f"  (sort: {self._sort_mode})", style="dim")
        text.append("\n\n")

        if not self._dirs:
            text.append("  No project directories found.\n", style="dim")
            return text

        home = os.path.expanduser("~")

        # Pre-compute display values to determine column widths
        entries: list[tuple[str, str, str, str]] = []
        for d in self._dirs:
            display = d["cwd"]
            if display.startswith(home):
                display = "~" + display[len(home):]

            lang = detect_language(d["cwd"])
            lang_badge = f"[{lang}]" if lang else ""

            label = "session" if d["count"] == 1 else "sessions"
            count_str = f"{d['count']} {label}"

            rel = relative_time(d["last_active"])

            entries.append((display, lang_badge, count_str, rel))

        # Calculate column widths for alignment
        max_path = max(len(e[0]) for e in entries)
        max_badge = max(len(e[1]) for e in entries) if any(e[1] for e in entries) else 0
        max_count = max(len(e[2]) for e in entries)

        for i, (display, lang_badge, count_str, rel) in enumerate(entries):
            is_cursor = i == self._cursor
            style = "reverse" if is_cursor else ""
            dim_style = "reverse" if is_cursor else "dim"

            path_padded = display.ljust(max_path)
            badge_padded = lang_badge.ljust(max_badge) if max_badge else ""
            count_padded = count_str.rjust(max_count)

            line = Text()
            line.append("  ", style=style)
            line.append(path_padded, style=style)
            if max_badge:
                line.append("  ", style=style)
                line.append(badge_padded, style=dim_style)
            line.append("  ", style=style)
            line.append(count_padded, style=dim_style)
            line.append("   ", style=style)
            line.append(rel, style=dim_style)
            line.append("\n")
            text.append_text(line)

        text.append("\n")
        text.append("  Enter", style="bold")
        text.append(" select   ", style="dim")
        text.append("s", style="bold")
        text.append(" sort   ", style="dim")
        text.append("Esc", style="bold")
        text.append(" cancel", style="dim")

        return text

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if not self._dirs:
            event.stop()
            return
        if event.key in ("up", "k"):
            self._cursor = max(0, self._cursor - 1)
            self._refresh_content()
            event.stop()
        elif event.key in ("down", "j"):
            self._cursor = min(len(self._dirs) - 1, self._cursor + 1)
            self._refresh_content()
            event.stop()
        elif event.key == "g":
            self._cursor = 0
            self._refresh_content()
            event.stop()
        elif event.key in ("G", "shift+g"):
            self._cursor = max(0, len(self._dirs) - 1)
            self._refresh_content()
            event.stop()
        elif event.key == "ctrl+u":
            self._cursor = max(0, self._cursor - 10)
            self._refresh_content()
            event.stop()
        elif event.key == "ctrl+d":
            self._cursor = min(len(self._dirs) - 1, self._cursor + 10)
            self._refresh_content()
            event.stop()
        elif event.key == "s":
            modes = ["frecency", "recency", "frequency"]
            idx = modes.index(self._sort_mode) if self._sort_mode in modes else 0
            self._sort_mode = modes[(idx + 1) % len(modes)]
            self._apply_sort()
            self._cursor = 0
            self._refresh_content()
            event.stop()
        elif event.key == "enter":
            if 0 <= self._cursor < len(self._dirs):
                self.dismiss(self._dirs[self._cursor]["cwd"])
            else:
                self.dismiss(None)
            event.stop()
        else:
            event.stop()
