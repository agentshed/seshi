import os
import sqlite3

from textual.widget import Widget
from textual.reactive import reactive
from textual import events
from textual.timer import Timer
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
    _cursor_visible: bool = True
    _blink_timer: Timer | None = None

    def _start_blink(self) -> None:
        self._cursor_visible = True
        self._blink_timer = self.set_interval(0.5, self._toggle_cursor)

    def _stop_blink(self) -> None:
        if self._blink_timer:
            self._blink_timer.stop()
            self._blink_timer = None
        self._cursor_visible = True

    def _toggle_cursor(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.refresh()

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
            cursor = "_" if self._cursor_visible else " "
            text.append(f"  rename: {self._input_buffer}{cursor}\n\n", style="bold")

        if not self._projects:
            text.append("  No projects found.\n", style="dim")
            text.append("  Start a Claude Code session in a project directory,\n", style="dim")
            text.append("  or run ", style="dim")
            text.append("seshi scan", style="bold")
            text.append(" to import existing ones.\n", style="dim")
            return text

        max_count = max(p["count"] for p in self._projects)
        w = self.size.width if self.size.width > 0 else 120
        bar_width = min(20, max(8, (w - 50) * 30 // 100))
        home = os.path.expanduser("~")
        max_rel_len = max(len(relative_time(p["last_active"])) for p in self._projects)
        # indent(2)+fav(2)+lang(4)+gap(2)+bar+gap(2)+count(3)+space(1)+label(8)+gap(2)+rel
        fixed = 2 + 2 + 4 + 2 + bar_width + 2 + 3 + 1 + 8 + 2 + max_rel_len
        display_w = max(15, w - fixed)

        for i, p in enumerate(self._projects):
            is_cursor = i == self.cursor
            style = "reverse" if is_cursor else ""

            fav = "★ " if p["is_favorite"] else "  "
            lang = detect_language(p["cwd"])
            lang_str = f"{lang:>3} " if lang else "    "

            display = p["custom_name"] or p["cwd"]
            if display.startswith(home):
                display = "~" + display[len(home):]
            if len(display) > display_w:
                half = (display_w - 1) // 2
                display = display[:half] + "…" + display[-(display_w - 1 - half):]

            rel = relative_time(p["last_active"])
            label = "session" if p["count"] == 1 else "sessions"
            bar_len = int((p["count"] / max(max_count, 1)) * bar_width)
            bar = "█" * bar_len + "░" * (bar_width - bar_len)

            row = f"  {fav}{lang_str}{display:<{display_w}}  {bar}  {p['count']:>3} {label}  {rel:>{max_rel_len}}"
            text.append(row[:w] + "\n", style=style)

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
        elif event.key == "g":
            self.cursor = 0
            self.refresh()
            event.stop()
        elif event.key in ("G", "shift+g"):
            self.cursor = max(0, len(self._projects) - 1)
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
                self._start_blink()
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
            self._stop_blink()
            self.refresh()
            event.stop()
        elif event.key == "enter":
            if self._input_mode == "rename":
                self._apply_rename()
            self._input_mode = ""
            self._input_buffer = ""
            self._stop_blink()
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
        display = name or cwd.rsplit("/", 1)[-1]
        try:
            self.app.notify(f"Project renamed to '{display}'", severity="information", timeout=2)
        except Exception:
            pass
