import os
import sys
import sqlite3

from textual.app import App, ComposeResult
from textual import work
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.widgets import Static

from seshi.db import open_db, get_setting, record_resume
from seshi.models import Session
from seshi.themes import get_theme
from seshi.tui.styles import theme_css
from seshi.tui.header import Header
from seshi.tui.footer import Footer
from seshi.tui.search_bar import SearchBar, SearchChanged
from seshi.tui.sessions import SessionsList
from seshi.tui.preview import Preview
from seshi.tui.commands import SeshiCommands


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

    COMMANDS = {SeshiCommands}

    CSS_PATH = "seshi.tcss"
    CSS = theme_css(get_theme("coral"))

    chosen_session: Session | None = None
    current_view: reactive[str] = reactive("sessions")
    _quit_toast_active: bool = False

    def __init__(self, ctx_obj: dict | None = None, conn: sqlite3.Connection | None = None, **kwargs):
        self.ctx_obj = ctx_obj or {}
        self._conn = conn
        self._owns_conn = conn is None
        self._view_counter = 0
        self._no_color = bool(os.environ.get("NO_COLOR"))
        self._preview_user_override: bool | None = None
        theme_name = "coral"
        if self._no_color:
            theme_name = "mono"
        elif conn:
            theme_name = get_setting(conn, "theme") or "coral"
        self._palette = get_theme(theme_name)
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Header(id="header")
        yield Static("", id="tab-bar")
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

        if self._no_color:
            theme_name = "mono"
        else:
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

        self._preview = Preview(id="preview")
        self._preview.session = self._sessions_list.current_session

        self._sessions_pane = Horizontal(id="sessions-pane")
        main.mount(self._sessions_pane)
        self._sessions_pane.mount(self._sessions_list)
        self._sessions_pane.mount(self._preview)
        self._update_preview_layout()

        self._sessions_list.focus()
        self._apply_palette()
        self._update_counts()
        self._update_tab_bar()

        try:
            self.query_one(Header).indexing = True
        except Exception:
            pass
        self._index_transcripts_async()

        initial_query = self.ctx_obj.get("search_query")
        if initial_query:
            search = self.query_one(SearchBar)
            search.active = True
            search.search_text = initial_query
            search.post_message(SearchChanged(initial_query))
            search.focus()

    @work(thread=True)
    def _index_transcripts_async(self) -> None:
        import logging
        from seshi.paths import DB_PATH
        from seshi.transcript_index import index_pending
        from seshi.prompt_index import index_pending_prompts
        from seshi.session_index import index_pending_search
        self.call_from_thread(self._set_indexing_flag, True)
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=3000")
            try:
                index_pending(conn)
                index_pending_prompts(conn)
                index_pending_search(conn)
            finally:
                conn.close()
        except Exception:
            logging.getLogger(__name__).debug("transcript indexing failed", exc_info=True)
        finally:
            self.call_from_thread(self._set_indexing_flag, False)

    def _set_indexing_flag(self, value: bool) -> None:
        try:
            self.query_one(Header).indexing = value
        except Exception:
            pass

    def _apply_palette(self):
        accent = self._palette.accent
        try:
            self.query_one(Header).accent = accent
            self.query_one(Footer).accent = accent
            self.query_one(SearchBar).accent = accent
            if hasattr(self, '_preview'):
                self._preview.user_color = self._palette.user
                self._preview.assistant_color = self._palette.assistant
        except Exception:
            pass
        try:
            preview = self.query_one(Preview)
            preview.user_color = self._palette.user
            preview.assistant_color = self._palette.assistant
        except Exception:
            pass

    def _update_preview_layout(self) -> None:
        if not hasattr(self, '_preview') or not hasattr(self, '_sessions_list'):
            return
        width = self.size.width if self.size.width > 0 else 120
        if self._preview_user_override is not None:
            show = self._preview_user_override
        else:
            show = width >= 100
        self._preview.display = show
        if show:
            list_width = max(30, int(width * 0.4))
            self._sessions_list.styles.width = list_width
        else:
            self._sessions_list.styles.width = "1fr"
        try:
            self.query_one(Footer).preview_visible = show
        except Exception:
            pass

    def on_resize(self, event) -> None:
        self._preview_user_override = None
        if self.current_view == "sessions":
            self._update_preview_layout()

    def _update_tab_bar(self):
        shown_count = 0
        project_count = 0
        if hasattr(self, '_sessions_list'):
            shown_count = len(self._sessions_list.sessions)
            project_count = len(set(s.cwd for s in self._sessions_list.sessions))
        views = {
            "sessions": f"1 sessions {shown_count}",
            "overview": "2 overview",
            "projects": f"3 projects {project_count}",
            "help": "? help",
        }
        from rich.text import Text
        text = Text()
        for key, label in views.items():
            text.append("  ")
            if key == self.current_view:
                text.append(f"[{label}]", style=f"bold {self._palette.accent}")
            else:
                text.append(f" {label} ", style="dim")
        tab_bar = self.query_one("#tab-bar", Static)
        tab_bar.update(text)

    def _update_counts(self):
        header = self.query_one(Header)
        total = len(self._sessions_list._all_sessions) if hasattr(self, '_sessions_list') else 0
        shown = len(self._sessions_list.sessions) if hasattr(self, '_sessions_list') else 0
        header.session_count = total
        header.shown_count = shown
        if hasattr(self, '_sessions_list'):
            header.sort_mode = self._sessions_list.sort_mode
        search = self.query_one(SearchBar)
        search.total = total
        search.shown = shown
        if hasattr(self, '_sessions_list'):
            search.sort_mode = self._sessions_list.sort_mode
            search._has_filter_cwd = bool(self._sessions_list.filter_cwd)
        self._update_tab_bar()

    def on_search_changed(self, message: SearchChanged) -> None:
        if hasattr(self, '_sessions_list'):
            self._sessions_list.filter(message.query, scope=message.scope)
            self._update_counts()
            s = self._sessions_list.current_session
            if hasattr(self, '_preview'):
                self._preview.session = s
                self._preview.highlight_query = message.query

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
        from textual.screen import ModalScreen
        try:
            if isinstance(self.screen, ModalScreen):
                self.screen.dismiss(False)
                return
        except Exception:
            pass

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
        elif search.active or search.has_focus or search.search_text or search.scope != "all":
            search.active = False
            search.search_text = ""
            search.scope = "all"
            search.post_message(SearchChanged("", "all"))
            sl.focus()
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

    def _is_in_input_mode(self) -> bool:
        if hasattr(self, '_sessions_list') and self._sessions_list._input_mode:
            return True
        try:
            search = self.query_one(SearchBar)
            if search.active:
                return True
        except Exception:
            pass
        return False

    def _forward_char_to_input(self, char: str) -> None:
        if hasattr(self, '_sessions_list') and self._sessions_list._input_mode:
            self._sessions_list._input_buffer += char
            self._sessions_list.refresh()
            return
        try:
            search = self.query_one(SearchBar)
            if search.active:
                search.search_text += char
                search.post_message(SearchChanged(search.search_text, search.scope))
        except Exception:
            pass

    def action_next_view(self) -> None:
        if self._is_in_input_mode():
            return
        views = ["sessions", "overview", "projects", "help"]
        idx = views.index(self.current_view) if self.current_view in views else 0
        self.current_view = views[(idx + 1) % len(views)]
        self._switch_view()

    def action_prev_view(self) -> None:
        if self._is_in_input_mode():
            return
        views = ["sessions", "overview", "projects", "help"]
        idx = views.index(self.current_view) if self.current_view in views else 0
        self.current_view = views[(idx - 1) % len(views)]
        self._switch_view()

    def action_view_sessions(self) -> None:
        if self._is_in_input_mode():
            self._forward_char_to_input("1")
            return
        if self.current_view != "sessions":
            self.current_view = "sessions"
            self._switch_view()

    def action_view_overview(self) -> None:
        if self._is_in_input_mode():
            self._forward_char_to_input("2")
            return
        if self.current_view != "overview":
            self.current_view = "overview"
            self._switch_view()

    def action_view_projects(self) -> None:
        if self._is_in_input_mode():
            self._forward_char_to_input("3")
            return
        if self.current_view != "projects":
            self.current_view = "projects"
            self._switch_view()

    def action_view_help(self) -> None:
        if self._is_in_input_mode():
            self._forward_char_to_input("?")
            return
        if self.current_view != "help":
            self.current_view = "help"
            self._switch_view()

    def _switch_view(self) -> None:
        if hasattr(self, '_sessions_list') and self._sessions_list._input_mode:
            self._sessions_list._input_mode = ""
            self._sessions_list._input_buffer = ""
            self._sessions_list._update_footer("normal")

        self._view_counter += 1
        vid = self._view_counter

        main = self.query_one("#main-content")
        for child in list(main.children):
            child.remove()

        if self.current_view == "sessions":
            self._sessions_pane = Horizontal(id="sessions-pane")
            main.mount(self._sessions_pane)
            self._sessions_pane.mount(self._sessions_list)
            if hasattr(self, '_preview'):
                self._sessions_pane.mount(self._preview)
            self._update_preview_layout()
            self._sessions_list.focus()
        elif self.current_view == "overview":
            from seshi.tui.overview import OverviewView
            view = OverviewView(self._conn, id=f"overview-{vid}")
            main.mount(view)
            view.focus()
        elif self.current_view == "projects":
            from seshi.tui.projects import ProjectsView
            view = ProjectsView(self._conn, id=f"projects-view-{vid}")
            main.mount(view)
            view.focus()
        elif self.current_view == "help":
            from seshi.tui.help_view import HelpView
            view = HelpView(id=f"help-view-{vid}")
            view.accent = self._palette.accent
            main.mount(view)
            view.focus()

        self._update_tab_bar()

    def action_resume(self) -> None:
        if hasattr(self, '_sessions_list'):
            s = self._sessions_list.current_session
            if s:
                self.chosen_session = s
                self.exit()

    def action_rename(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._start_rename()

    def action_favorite(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._toggle_favorite()

    def action_tag(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._start_tag()

    def action_archive(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._toggle_archive()

    def action_delete(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._delete_selected()

    def action_cycle_sort(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._cycle_sort()

    def action_toggle_preview(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._toggle_preview()

    def action_toggle_expand(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._toggle_expand()

    def action_toggle_expand_all(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._toggle_expand_all()

    def action_undo(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._undo_last()

    def action_toggle_hide_missing(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._toggle_hide_missing()

    def action_toggle_hide_stale(self) -> None:
        if hasattr(self, '_sessions_list') and self.current_view == "sessions":
            self._sessions_list._toggle_hide_stale()

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
        with open_db() as conn:
            record_resume(conn, session.session_id)
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
