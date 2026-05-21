import os
import sqlite3

from textual.widget import Widget
from textual.reactive import reactive
from textual import events
from rich.text import Text

from seshi.lang_detect import detect_language
from seshi.time_utils import relative_time


class ProjectsView(Widget):
    DEFAULT_CSS = """
    ProjectsView {
        padding: 1 2;
    }
    """

    can_focus = True
    cursor: reactive[int] = reactive(0)
    _input_mode: str = ""
    _input_buffer: str = ""

    def __init__(self, conn: sqlite3.Connection, **kwargs):
        super().__init__(**kwargs)
        self.conn = conn
        self._projects: list[dict] = []
        self._load_projects()

    def _load_projects(self):
        rows = self.conn.execute("""
            SELECT cwd, COUNT(*) as count, MAX(last_activity_at) as last_active
            FROM sessions WHERE is_archived = 0
            GROUP BY cwd ORDER BY last_active DESC
        """).fetchall()

        favs = {
            r["cwd"]: r["custom_name"]
            for r in self.conn.execute("SELECT cwd, custom_name FROM project_favorites").fetchall()
        }

        self._projects = []
        for r in rows:
            self._projects.append({
                "cwd": r["cwd"],
                "count": r["count"],
                "last_active": r["last_active"],
                "is_favorite": r["cwd"] in favs,
                "custom_name": favs.get(r["cwd"]),
            })

        fav_projects = [p for p in self._projects if p["is_favorite"]]
        non_fav = [p for p in self._projects if not p["is_favorite"]]
        self._projects = fav_projects + non_fav

    def render(self) -> Text:
        text = Text()

        if self._input_mode == "rename":
            text.append(f"  rename: {self._input_buffer}▮\n\n", style="bold")

        if not self._projects:
            text.append("  no projects found\n", style="dim")
            return text

        max_count = max(p["count"] for p in self._projects)
        bar_width = 20

        for i, p in enumerate(self._projects):
            is_cursor = i == self.cursor
            style = "reverse" if is_cursor else ""

            fav = "★ " if p["is_favorite"] else "  "
            lang = detect_language(p["cwd"])
            lang_str = f"{lang:>3} " if lang else "    "

            home = os.path.expanduser("~")
            display = p["custom_name"] or p["cwd"]
            if display.startswith(home):
                display = "~" + display[len(home):]
            if len(display) > 40:
                display = display[:19] + "…" + display[-20:]

            bar_len = int((p["count"] / max(max_count, 1)) * bar_width)
            bar = "█" * bar_len + "░" * (bar_width - bar_len)

            rel = relative_time(p["last_active"])

            label = "session" if p["count"] == 1 else "sessions"
            text.append(f"  {fav}{lang_str}{display:<40}  {bar}  {p['count']:>3} {label}  {rel}\n", style=style)

        return text

    def on_key(self, event: events.Key) -> None:
        if self._input_mode:
            self._handle_input_key(event)
            return

        if event.key in ("up", "k"):
            self.cursor = max(0, self.cursor - 1)
            self.refresh()
            event.stop()
        elif event.key in ("down", "j"):
            self.cursor = min(len(self._projects) - 1, self.cursor + 1)
            self.refresh()
            event.stop()
        elif event.key == "f":
            if 0 <= self.cursor < len(self._projects):
                cwd = self._projects[self.cursor]["cwd"]
                existing = self.conn.execute("SELECT 1 FROM project_favorites WHERE cwd = ?", (cwd,)).fetchone()
                if existing:
                    self.conn.execute("DELETE FROM project_favorites WHERE cwd = ?", (cwd,))
                else:
                    self.conn.execute("INSERT INTO project_favorites (cwd) VALUES (?)", (cwd,))
                self.conn.commit()
                self._load_projects()
                self.refresh()
                event.stop()
        elif event.key == "r":
            if 0 <= self.cursor < len(self._projects):
                self._input_mode = "rename"
                self._input_buffer = self._projects[self.cursor].get("custom_name") or ""
                self.refresh()
                event.stop()
        elif event.key == "enter":
            if 0 <= self.cursor < len(self._projects):
                cwd = self._projects[self.cursor]["cwd"]
                self.app.ctx_obj["here_cwd"] = cwd
                if hasattr(self.app, '_sessions_list'):
                    self.app._sessions_list.filter_cwd = cwd
                self.app.action_view_sessions()
                if hasattr(self.app, '_sessions_list'):
                    self.app._sessions_list._load_sessions()
                    self.app._update_counts()
                event.stop()

    def _handle_input_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self._input_mode = ""
            self._input_buffer = ""
            self.refresh()
            event.stop()
        elif event.key == "enter":
            if self._input_mode == "rename":
                self._apply_rename()
            self._input_mode = ""
            self._input_buffer = ""
            self.refresh()
            event.stop()
        elif event.key == "backspace":
            self._input_buffer = self._input_buffer[:-1]
            self.refresh()
            event.stop()
        elif event.is_printable and event.character:
            self._input_buffer += event.character
            self.refresh()
            event.stop()

    def _apply_rename(self):
        if not (0 <= self.cursor < len(self._projects)):
            return
        cwd = self._projects[self.cursor]["cwd"]
        name = self._input_buffer.strip() or None
        existing = self.conn.execute("SELECT 1 FROM project_favorites WHERE cwd = ?", (cwd,)).fetchone()
        if existing:
            self.conn.execute("UPDATE project_favorites SET custom_name = ? WHERE cwd = ?", (name, cwd))
        else:
            self.conn.execute("INSERT INTO project_favorites (cwd, custom_name) VALUES (?, ?)", (cwd, name))
        self.conn.commit()
        self._load_projects()
