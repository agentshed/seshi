import os
import re
import sqlite3

from textual.widget import Widget
from textual.reactive import reactive
from textual import events
from rich.text import Text

from seshi.models import Session
from seshi.prompt_text import strip_markup_tags
from seshi.search import list_sessions, score_sessions
from seshi.transcript_index import search_transcripts
from seshi.time_utils import relative_time, time_bucket
from seshi.lang_detect import detect_language
from seshi.db import get_setting, set_setting
from seshi.tui.search_bar import SearchBar, SearchChanged


class SessionsList(Widget):
    DEFAULT_CSS = """
    SessionsList {
        height: 1fr;
        min-height: 10;
    }
    """

    can_focus = True

    cursor: reactive[int] = reactive(0)
    sessions: reactive[list] = reactive(list, init=False)
    selected: reactive[set] = reactive(set, init=False)
    sort_mode: reactive[str] = reactive("frecency")

    def __init__(self, conn: sqlite3.Connection, filter_cwd: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.conn = conn
        self.filter_cwd = filter_cwd
        self.sessions = []
        self.selected = set()
        self._all_sessions: list[Session] = []
        self._current_query: str = ""
        self._current_tags: list[str] | None = None
        self._load_sessions()

    def _load_sessions(self, query: str = "", tags: list[str] | None = None):
        hide_missing = get_setting(self.conn, "hide_missing_dirs") == "1"
        hide_stale = get_setting(self.conn, "hide_stale_sessions") == "1"
        sessions = list_sessions(
            self.conn,
            filter_cwd=self.filter_cwd,
            tags=tags,
            sort_mode=self.sort_mode,
        )

        if hide_missing:
            sessions = [s for s in sessions if os.path.isdir(s.cwd)]

        if hide_stale:
            from seshi.transcript import get_existing_session_ids
            existing = get_existing_session_ids()
            sessions = [s for s in sessions if s.session_id in existing]

        self._all_sessions = sessions

        if query:
            fts_scores = search_transcripts(self.conn, query)
            blended = score_sessions(sessions, query, fts_scores)
            blended.sort(key=lambda x: (-x[0].is_favorite, -x[1]))
            sessions = [s for s, _ in blended]

        self.sessions = sessions
        if self.cursor >= len(self.sessions):
            self.cursor = max(0, len(self.sessions) - 1)
        self.refresh()

    def filter(self, query: str):
        text, tags = _parse_search(query)
        self._current_query = text
        self._current_tags = tags if tags else None
        self._load_sessions(query=text, tags=self._current_tags)

    def watch_cursor(self, cursor: int) -> None:
        try:
            if hasattr(self.app, '_preview'):
                self.app._preview.session = self.current_session
        except Exception:
            pass

    @property
    def current_session(self) -> Session | None:
        if 0 <= self.cursor < len(self.sessions):
            return self.sessions[self.cursor]
        return None

    _scroll_offset: int = 0

    def render(self) -> Text:
        text = Text()

        if self._input_mode:
            label = "rename" if self._input_mode == "rename" else "tag"
            text.append(f"  {label}: {self._input_buffer}▮\n\n", style="bold")

        if not self.sessions:
            if self._current_query or self._current_tags:
                text.append("  No sessions match your search.\n", style="dim")
                text.append("  Press Esc to clear the filter.\n", style="dim")
            elif self.filter_cwd:
                text.append("  No sessions for this project.\n", style="dim")
                text.append("  Press Esc to show all sessions.\n", style="dim")
            elif not self._all_sessions:
                text.append("  No sessions yet.\n", style="dim")
                text.append("  Start a Claude Code session, or run ", style="dim")
                text.append("seshi scan", style="bold")
                text.append(" to import existing ones.\n", style="dim")
            else:
                text.append("  No sessions found (all filtered out).\n", style="dim")
                text.append("  Press H to toggle hidden-dir filter, S for stale filter.\n", style="dim")
            return text

        visible_height = max(self.size.height - 2, 5) if self.size.height > 0 else 20

        if self.cursor < self._scroll_offset:
            self._scroll_offset = self.cursor
        elif self.cursor >= self._scroll_offset + visible_height:
            self._scroll_offset = self.cursor - visible_height + 1

        home = os.path.expanduser("~")

        lines: list[tuple[int, Session]] = list(enumerate(self.sessions))

        w = self.size.width if self.size.width > 0 else 120
        narrow = w < 60
        max_rel_len = max((len(relative_time(s.last_activity_at)) for _, s in lines), default=8)

        if narrow:
            # Compact: cursor(1)+sel(3)+fav(2)+space(1)+gap(2)+rel = 9+max_rel_len
            compact_overhead = 9 + max_rel_len
            title_w = max(10, w - compact_overhead)
        else:
            # prefix: cursor(1)+sel(3)+fav(3)+lang(3)+gap(2)=12; gaps: 2+2=4
            overhead = 12 + 4 + max_rel_len
            avail = max(30, w - overhead)
            title_w = min(50, max(12, avail * 40 // 100))
            cwd_w = min(40, max(12, avail * 33 // 100))

        current_bucket = ""
        visible_rows: list[tuple[str, str, bool]] = []

        for i, s in lines:
            bucket_header = None
            if s.is_favorite and current_bucket != "favorites":
                current_bucket = "favorites"
                bucket_header = "  ── ★ favorites ──"
            elif not s.is_favorite:
                bucket = time_bucket(s.last_activity_at)
                if bucket != current_bucket:
                    current_bucket = bucket
                    bucket_header = f"  ── {bucket} ──"

            if bucket_header:
                visible_rows.append((bucket_header, "dim", False))

            is_selected = s.session_id in self.selected
            is_cursor = i == self.cursor
            style = "reverse" if is_cursor else ""

            cursor_mark = "▸" if is_cursor else " "
            sel_mark = "[x]" if is_selected else "   "
            rel = relative_time(s.last_activity_at)
            title = (s.custom_name or strip_markup_tags(s.first_prompt or "") or "(untitled)")[:title_w]

            if narrow:
                fav = " *" if s.is_favorite else "  "
                base = f"{cursor_mark}{sel_mark}{fav} {title:<{title_w}}  {rel:>{max_rel_len}}"
                line = base[:w]
            else:
                fav = " * " if s.is_favorite else "   "
                lang = detect_language(s.cwd)
                lang_str = f"{lang:>3}" if lang else "   "
                cwd = s.cwd
                if cwd.startswith(home):
                    cwd = "~" + cwd[len(home):]
                if len(cwd) > cwd_w:
                    half = (cwd_w - 1) // 2
                    cwd = cwd[:half] + "…" + cwd[-(cwd_w - 1 - half):]

                tags_str = ""
                tag_rows = self.conn.execute(
                    "SELECT tag FROM tags WHERE session_id = ?", (s.session_id,)
                ).fetchall()
                if tag_rows:
                    tags_str = " " + " ".join(f"#{r['tag']}" for r in tag_rows)

                base = f"{cursor_mark}{sel_mark}{fav}{lang_str}  {title:<{title_w}}  {cwd:<{cwd_w}}  {rel:>{max_rel_len}}"
                tags_budget = w - len(base)
                if tags_str and tags_budget > 3:
                    tags_str = tags_str[:tags_budget]
                else:
                    tags_str = ""
                line = (base + tags_str)[:w]
            visible_rows.append((line, style, is_cursor))

        cursor_row_idx = 0
        for idx, (_, _, is_cur) in enumerate(visible_rows):
            if is_cur:
                cursor_row_idx = idx
                break

        start = max(0, cursor_row_idx - visible_height // 2)
        if start + visible_height > len(visible_rows):
            start = max(0, len(visible_rows) - visible_height)
        end = min(start + visible_height, len(visible_rows))

        for row_line, row_style, _ in visible_rows[start:end]:
            if self._current_query and row_style != "dim":
                line_text = Text(row_line + "\n", style=row_style)
                line_text.highlight_words([self._current_query], style="bold underline", case_sensitive=False)
                text.append_text(line_text)
            else:
                text.append(row_line + "\n", style=row_style)

        remaining = visible_height - (end - start)
        for _ in range(remaining):
            text.append("~\n", style="dim")

        return text

    _input_mode: str = ""
    _input_buffer: str = ""

    def on_key(self, event: events.Key) -> None:
        if getattr(self.app, "_quit_toast_active", False):
            self.app._quit_toast_active = False
            event.stop()
            return

        if self._input_mode:
            self._handle_input_key(event)
            return

        handled = True
        if event.key in ("up", "k"):
            self.cursor = max(0, self.cursor - 1)
        elif event.key in ("down", "j"):
            self.cursor = min(len(self.sessions) - 1, self.cursor + 1)
        elif event.key == "g":
            self.cursor = 0
        elif event.key in ("G", "shift+g"):
            self.cursor = max(0, len(self.sessions) - 1)
        elif event.key == "ctrl+u":
            self.cursor = max(0, self.cursor - 10)
        elif event.key == "ctrl+d":
            self.cursor = min(len(self.sessions) - 1, self.cursor + 10)
        elif event.key == "space":
            s = self.current_session
            if s:
                if s.session_id in self.selected:
                    self.selected.discard(s.session_id)
                else:
                    self.selected.add(s.session_id)
        elif event.key == "ctrl+a":
            for s in self.sessions:
                self.selected.add(s.session_id)
        elif event.key == "r":
            self._start_rename()
        elif event.key == "t":
            self._start_tag()
        elif event.key == "f":
            self._toggle_favorite()
        elif event.key == "u":
            self._toggle_archive()
        elif event.key == "d":
            self._delete_selected()
        elif event.key == "s":
            modes = ["frecency", "recency", "frequency"]
            idx = modes.index(self.sort_mode) if self.sort_mode in modes else 0
            self.sort_mode = modes[(idx + 1) % len(modes)]
            set_setting(self.conn, "sort_mode", self.sort_mode)
            self._reload_with_current_filter()
        elif event.key == "H":
            current = get_setting(self.conn, "hide_missing_dirs")
            new_val = "0" if current == "1" else "1"
            set_setting(self.conn, "hide_missing_dirs", new_val)
            self._reload_with_current_filter()
        elif event.key == "S":
            current = get_setting(self.conn, "hide_stale_sessions")
            new_val = "0" if current == "1" else "1"
            set_setting(self.conn, "hide_stale_sessions", new_val)
            self._reload_with_current_filter()
        elif event.key == "p":
            if hasattr(self.app, '_preview'):
                self.app._preview.display = not self.app._preview.display
                if self.app._preview.display:
                    self.styles.width = 45
                else:
                    self.styles.width = "1fr"
        elif event.key == "slash":
            search = self.app.query_one(SearchBar)
            search.active = True
            search.focus()
        elif event.key == "escape":
            pass  # handled by app-level action_back_or_quit
        elif event.key == "enter":
            s = self.current_session
            if s:
                self.app.chosen_session = s
                self.app.exit()
                return
        else:
            if event.is_printable and event.character:
                search = self.app.query_one(SearchBar)
                search.active = True
                search.search_text += event.character
                search.post_message(SearchChanged(search.search_text))
            elif event.key == "backspace":
                search = self.app.query_one(SearchBar)
                if search.search_text:
                    search.search_text = search.search_text[:-1]
                    search.post_message(SearchChanged(search.search_text))
            else:
                handled = False

        if handled:
            self.refresh()
            event.stop()

    def _handle_input_key(self, event: events.Key):
        if event.key == "escape":
            self._input_mode = ""
            self._input_buffer = ""
            self._update_footer("normal")
            self.refresh()
            event.stop()
            return
        if event.key == "enter":
            if self._input_mode == "rename":
                self._apply_rename()
            elif self._input_mode == "tag":
                self._apply_tag()
            self._input_mode = ""
            self._input_buffer = ""
            self._update_footer("normal")
            self.refresh()
            event.stop()
            return
        if event.key == "backspace":
            self._input_buffer = self._input_buffer[:-1]
            self.refresh()
            event.stop()
            return
        if event.is_printable and event.character:
            self._input_buffer += event.character
            self.refresh()
            event.stop()

    def _update_footer(self, mode: str):
        try:
            footer = self.app.query_one("Footer")
            footer.mode = mode
        except Exception:
            pass

    def _start_rename(self):
        s = self.current_session
        if not s:
            return
        self._input_mode = "rename"
        self._input_buffer = s.custom_name or ""
        self._update_footer("rename")
        self.refresh()

    def _start_tag(self):
        s = self.current_session
        if not s:
            return
        self._input_mode = "tag"
        self._input_buffer = ""
        self._update_footer("tag")
        self.refresh()

    def _reload_with_current_filter(self):
        self._load_sessions(query=self._current_query, tags=self._current_tags)
        try:
            self.app._update_counts()
        except Exception:
            pass

    def _apply_rename(self):
        s = self.current_session
        if not s:
            return
        name = self._input_buffer.strip() or None
        self.conn.execute("UPDATE sessions SET custom_name = ? WHERE session_id = ?", (name, s.session_id))
        self.conn.commit()
        self._reload_with_current_filter()

    def _apply_tag(self):
        tag = self._input_buffer.strip()
        if not tag or not re.match(r"^[\w\-]+$", tag):
            return
        targets = list(self.selected) if self.selected else [self.current_session.session_id] if self.current_session else []
        for sid in targets:
            existing = self.conn.execute("SELECT 1 FROM tags WHERE session_id = ? AND tag = ?", (sid, tag)).fetchone()
            if existing:
                self.conn.execute("DELETE FROM tags WHERE session_id = ? AND tag = ?", (sid, tag))
            else:
                self.conn.execute("INSERT INTO tags (session_id, tag) VALUES (?, ?)", (sid, tag))
        self.conn.commit()
        self._reload_with_current_filter()

    def _toggle_favorite(self):
        s = self.current_session
        if not s:
            return
        targets = list(self.selected) if self.selected else [s.session_id]
        for sid in targets:
            self.conn.execute(
                "UPDATE sessions SET is_favorite = CASE WHEN is_favorite = 1 THEN 0 ELSE 1 END WHERE session_id = ?",
                (sid,),
            )
        self.conn.commit()
        self._reload_with_current_filter()

    def _toggle_archive(self):
        s = self.current_session
        if not s:
            return
        targets = list(self.selected) if self.selected else [s.session_id]
        if len(targets) > 1:
            from seshi.tui.confirm_bulk import ConfirmBulkScreen
            self.app.push_screen(
                ConfirmBulkScreen(f"Archive {len(targets)} sessions?"),
                lambda confirmed: self._execute_archive(targets) if confirmed else None,
            )
        else:
            self._execute_archive(targets)

    def _execute_archive(self, targets: list[str]) -> None:
        for sid in targets:
            self.conn.execute(
                "UPDATE sessions SET is_archived = CASE WHEN is_archived = 1 THEN 0 ELSE 1 END WHERE session_id = ?",
                (sid,),
            )
        self.conn.commit()
        self.selected.clear()
        self._reload_with_current_filter()

    def _delete_selected(self):
        s = self.current_session
        if not s:
            return
        targets = list(self.selected) if self.selected else [s.session_id]
        from seshi.tui.confirm_bulk import ConfirmBulkScreen
        self.app.push_screen(
            ConfirmBulkScreen(f"Delete {len(targets)} session{'s' if len(targets) > 1 else ''}?"),
            lambda confirmed: self._execute_delete(targets) if confirmed else None,
        )

    def _execute_delete(self, targets: list[str]) -> None:
        for sid in targets:
            self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
        self.conn.commit()
        self.selected.clear()
        self._reload_with_current_filter()


def _parse_search(query: str) -> tuple[str, list[str]]:
    parts = query.split()
    tags = [p[1:] for p in parts if p.startswith("#")]
    text = " ".join(p for p in parts if not p.startswith("#"))
    return text, tags
