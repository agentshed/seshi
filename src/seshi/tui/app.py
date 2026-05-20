import os
import sys
import sqlite3

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.widgets import Static

from seshi.db import open_db, get_setting
from seshi.models import Session
from seshi.themes import get_theme
from seshi.tui.styles import theme_css
from seshi.tui.header import Header
from seshi.tui.footer import Footer
from seshi.tui.search_bar import SearchBar, SearchChanged
from seshi.tui.sessions import SessionsList
from seshi.tui.preview import Preview


class SeshiApp(App):
    BINDINGS = [
        Binding("escape", "back_or_quit", "Back / Quit", show=False, priority=True),
        Binding("tab", "next_view", "Next view", show=False, priority=True),
        Binding("shift+tab", "prev_view", "Previous view", show=False, priority=True),
        Binding("1", "view_sessions", "Sessions", show=False, priority=True),
        Binding("2", "view_overview", "Overview", show=False, priority=True),
        Binding("3", "view_projects", "Projects", show=False, priority=True),
        Binding("question_mark", "view_help", "Help", show=False, priority=True),
    ]

    CSS = theme_css(get_theme("coral"))

    chosen_session: Session | None = None
    current_view: reactive[str] = reactive("sessions")
    _quit_toast_active: bool = False

    def __init__(self, ctx_obj: dict | None = None, conn: sqlite3.Connection | None = None, **kwargs):
        self.ctx_obj = ctx_obj or {}
        self._conn = conn
        self._owns_conn = conn is None
        theme_name = "coral"
        if conn:
            theme_name = get_setting(conn, "theme") or "coral"
        self._palette = get_theme(theme_name)
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Header(id="header")
        tab_text = "  1 sessions    2 overview    3 projects    ? help"
        yield Static(tab_text, id="tab-bar")
        yield SearchBar(id="search-bar")
        with Vertical(id="main-content"):
            yield Static("Loading...", id="placeholder")
        yield Footer(id="footer")

    def on_mount(self) -> None:
        if self._conn is None:
            from seshi.paths import DB_PATH
            self._conn = sqlite3.connect(str(DB_PATH))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")

        theme_name = get_setting(self._conn, "theme") or "coral"
        sort_mode = get_setting(self._conn, "sort_mode") or "frecency"

        self._sessions_list = SessionsList(
            self._conn,
            filter_cwd=self.ctx_obj.get("here_cwd"),
            id="session-list",
        )
        self._sessions_list.sort_mode = sort_mode

        placeholder = self.query_one("#placeholder")
        main = self.query_one("#main-content")
        placeholder.remove()
        main.mount(self._sessions_list)

        self._preview = Preview(id="preview")
        main.mount(self._preview)

        self._sessions_list.focus()
        self._apply_palette()
        self._update_counts()

    def _apply_palette(self):
        accent = self._palette.accent
        try:
            self.query_one(Header).accent = accent
            self.query_one(Footer).accent = accent
            self.query_one(SearchBar).accent = accent
        except Exception:
            pass

    def action_request_quit(self) -> None:
        self._quit_toast_active = True
        super().action_request_quit()

    def _update_counts(self):
        header = self.query_one(Header)
        total = len(self._sessions_list._all_sessions) if hasattr(self, '_sessions_list') else 0
        shown = len(self._sessions_list.sessions) if hasattr(self, '_sessions_list') else 0
        header.session_count = total
        header.shown_count = shown
        search = self.query_one(SearchBar)
        search.total = total
        search.shown = shown
        if hasattr(self, '_sessions_list'):
            search.sort_mode = self._sessions_list.sort_mode

    def on_search_changed(self, message: SearchChanged) -> None:
        if hasattr(self, '_sessions_list'):
            self._sessions_list.filter(message.query)
            self._update_counts()
            s = self._sessions_list.current_session
            if hasattr(self, '_preview'):
                self._preview.session = s

    def watch_current_view(self, view: str) -> None:
        footer = self.query_one(Footer)
        footer.view = view

    def action_request_quit(self) -> None:
        self._quit_toast_active = True
        self.notify(
            "Press Ctrl+Q to quit, Escape to cancel.",
            severity="warning",
            timeout=3,
        )
        self.set_timer(3, self._clear_quit_toast)

    def _clear_quit_toast(self) -> None:
        self._quit_toast_active = False

    def action_back_or_quit(self) -> None:
        if self._quit_toast_active:
            self._quit_toast_active = False
            return

        if self.current_view != "sessions":
            self.current_view = "sessions"
            self._switch_view()
            return

        if not hasattr(self, '_sessions_list'):
            self.exit()
            return

        sl = self._sessions_list
        search = self.query_one(SearchBar)

        if sl._input_mode:
            sl._input_mode = ""
            sl._input_buffer = ""
            sl._update_footer("normal")
            sl.refresh()
        elif search.active or search.has_focus:
            search.active = False
            sl.focus()
        elif search.query:
            search.query = ""
            search.post_message(SearchChanged(""))
            self._update_counts()
        elif sl.filter_cwd:
            sl.filter_cwd = None
            sl._load_sessions()
            self._update_counts()
        elif sl.selected:
            sl.selected.clear()
            sl.refresh()
        else:
            self.exit()

    def action_next_view(self) -> None:
        views = ["sessions", "overview", "projects", "help"]
        idx = views.index(self.current_view) if self.current_view in views else 0
        self.current_view = views[(idx + 1) % len(views)]
        self._switch_view()

    def action_prev_view(self) -> None:
        views = ["sessions", "overview", "projects", "help"]
        idx = views.index(self.current_view) if self.current_view in views else 0
        self.current_view = views[(idx - 1) % len(views)]
        self._switch_view()

    def action_view_sessions(self) -> None:
        self.current_view = "sessions"
        self._switch_view()

    def action_view_overview(self) -> None:
        self.current_view = "overview"
        self._switch_view()

    def action_view_projects(self) -> None:
        self.current_view = "projects"
        self._switch_view()

    def action_view_help(self) -> None:
        self.current_view = "help"
        self._switch_view()

    def _switch_view(self) -> None:
        main = self.query_one("#main-content")
        for child in list(main.children):
            child.remove()

        if self.current_view == "sessions":
            main.mount(self._sessions_list)
            if hasattr(self, '_preview'):
                main.mount(self._preview)
            self._sessions_list.focus()
        elif self.current_view == "overview":
            from seshi.tui.overview import OverviewView
            view = OverviewView(self._conn, id="overview")
            main.mount(view)
            view.focus()
        elif self.current_view == "projects":
            from seshi.tui.projects import ProjectsView
            view = ProjectsView(self._conn, id="projects-view")
            main.mount(view)
            view.focus()
        elif self.current_view == "help":
            from seshi.tui.help_view import HelpView
            view = HelpView(id="help-view")
            main.mount(view)
            view.focus()

    def on_unmount(self) -> None:
        if self._owns_conn and self._conn:
            self._conn.close()


def launch_tui(ctx_obj: dict | None = None):
    import json
    import subprocess

    if not os.isatty(sys.stdout.fileno()):
        try:
            tty_w = open("/dev/tty", "w")
            tty_r = open("/dev/tty", "r")
            sys.stdout = tty_w
            sys.stdin = tty_r
        except OSError:
            print("seshi: no controlling terminal — run `seshi` interactively from a shell.",
                  file=sys.stderr)
            raise SystemExit(1)

    while True:
        app = SeshiApp(ctx_obj=ctx_obj)
        app.run()

        if not app.chosen_session:
            break

        session = app.chosen_session
        try:
            argv = json.loads(session.launch_argv_json)
        except (json.JSONDecodeError, TypeError):
            argv = []
        if isinstance(argv, str):
            argv = argv.split()
        if not isinstance(argv, list):
            argv = []

        filtered = []
        skip_next = False
        for arg in argv:
            if skip_next:
                skip_next = False
                continue
            if arg == "--resume":
                skip_next = True
                continue
            if arg.startswith("--resume="):
                continue
            filtered.append(arg)

        if not filtered or filtered[0] != "claude":
            filtered.insert(0, "claude")
        filtered.extend(["--resume", session.session_id])

        prev_dir = os.getcwd()
        try:
            os.chdir(session.cwd)
        except OSError:
            pass

        try:
            subprocess.run(filtered)
        except FileNotFoundError:
            print(f"seshi: command not found: {filtered[0]}", file=sys.stderr)
        except KeyboardInterrupt:
            pass

        try:
            os.chdir(prev_dir)
        except OSError:
            pass
