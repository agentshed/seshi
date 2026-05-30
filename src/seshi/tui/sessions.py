import os
import re
import sqlite3
from dataclasses import dataclass

from textual.widget import Widget
from textual.reactive import reactive
from textual import events
from textual.timer import Timer
from rich.text import Text

from seshi.models import Session, Prompt
from seshi.prompt_text import strip_markup_tags, strip_system_blocks
from seshi.search import list_sessions, rank_sessions, query_matches_text
from seshi.time_utils import relative_time
from seshi.lang_detect import detect_language
from seshi.db import get_setting, set_setting
from seshi.tui.search_bar import SearchBar, SearchChanged


@dataclass
class DisplayRow:
    kind: str  # "bucket", "session", "prompt"
    session: Session | None = None
    prompt: Prompt | None = None
    label: str = ""


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
        self._prompts: dict[str, list[Prompt]] = {}
        self._collapsed: set[str] = set()
        self._display_rows: list[DisplayRow] = []
        self._matching_prompts: set[tuple[str, int]] = set()
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
        self.sessions = sessions
        self._load_prompts()

        if query:
            allowed_ids = {s.session_id for s in sessions}
            ranked = rank_sessions(self.conn, query, filter_cwd=self.filter_cwd)
            blended = [(s, score) for s, score in ranked if s.session_id in allowed_ids]
            blended.sort(key=lambda x: (-x[0].is_favorite, -x[1]))
            sessions = [s for s, _ in blended]
            self.sessions = sessions

        self._matching_prompts = set()
        if query:
            for sid, plist in self._prompts.items():
                for p in plist:
                    if query_matches_text(query, p.text):
                        self._matching_prompts.add((sid, p.prompt_index))
            for sid, _ in self._matching_prompts:
                self._collapsed.discard(sid)

        self._build_display_rows()
        nav_rows = [r for r in self._display_rows if r.kind != "bucket"]
        if self.cursor >= len(nav_rows):
            self.cursor = max(0, len(nav_rows) - 1)
        self.refresh()

    def _load_prompts(self):
        self._prompts = {}
        if not self.sessions:
            return
        ids = [s.session_id for s in self.sessions]
        placeholders = ",".join("?" * len(ids))
        try:
            rows = self.conn.execute(
                f"SELECT * FROM prompts WHERE session_id IN ({placeholders}) ORDER BY session_id, prompt_index",
                ids,
            ).fetchall()
            for row in rows:
                sid = row["session_id"]
                if sid not in self._prompts:
                    self._prompts[sid] = []
                self._prompts[sid].append(Prompt.from_row(row))
        except Exception:
            pass

    def _build_display_rows(self):
        rows: list[DisplayRow] = []
        home = os.path.expanduser("~")

        favorites = [s for s in self.sessions if s.is_favorite]
        non_favorites = [s for s in self.sessions if not s.is_favorite]

        if favorites:
            rows.append(DisplayRow(kind="bucket", label="  ── ★ favorites ──"))
            for s in favorites:
                rows.append(DisplayRow(kind="session", session=s))
                if s.session_id not in self._collapsed:
                    for p in self._prompts.get(s.session_id, []):
                        rows.append(DisplayRow(kind="prompt", session=s, prompt=p))

        groups: dict[str, list[Session]] = {}
        seen_cwds: list[str] = []
        for s in non_favorites:
            if s.cwd not in groups:
                seen_cwds.append(s.cwd)
                groups[s.cwd] = []
            groups[s.cwd].append(s)

        for cwd in seen_cwds:
            display_cwd = cwd
            if display_cwd.startswith(home):
                display_cwd = "~" + display_cwd[len(home):]
            lang = detect_language(cwd)
            lang_str = f" ({lang})" if lang else ""
            rel = relative_time(groups[cwd][0].last_activity_at)
            max_path = 40
            if len(display_cwd) > max_path:
                half = (max_path - 1) // 2
                display_cwd = display_cwd[:half] + "…" + display_cwd[-(max_path - 1 - half):]
            rows.append(DisplayRow(kind="bucket", label=f"  ── {display_cwd}{lang_str} {rel} ──"))
            for s in groups[cwd]:
                rows.append(DisplayRow(kind="session", session=s))
                if s.session_id not in self._collapsed:
                    for p in self._prompts.get(s.session_id, []):
                        rows.append(DisplayRow(kind="prompt", session=s, prompt=p))

        self._display_rows = rows

    def filter(self, query: str):
        text, tags = _parse_search(query)
        self._current_query = text
        self._current_tags = tags if tags else None
        self._load_sessions(query=text, tags=self._current_tags)

    def _cursor_to_display_index(self, cursor: int) -> int:
        nav_idx = 0
        for i, row in enumerate(self._display_rows):
            if row.kind == "bucket":
                continue
            if nav_idx == cursor:
                return i
            nav_idx += 1
        return len(self._display_rows) - 1

    def _nav_row_count(self) -> int:
        return sum(1 for r in self._display_rows if r.kind != "bucket")

    def watch_cursor(self, cursor: int) -> None:
        try:
            if hasattr(self.app, '_preview'):
                self.app._preview.session = self.current_session
                di = self._cursor_to_display_index(cursor)
                row = self._display_rows[di] if 0 <= di < len(self._display_rows) else None
                if hasattr(self.app._preview, 'focus_prompt_index'):
                    self.app._preview.focus_prompt_index = row.prompt.prompt_index if row and row.prompt else None
        except Exception:
            pass

    @property
    def current_session(self) -> Session | None:
        di = self._cursor_to_display_index(self.cursor)
        if 0 <= di < len(self._display_rows):
            return self._display_rows[di].session
        return None

    @property
    def _current_display_row(self) -> DisplayRow | None:
        di = self._cursor_to_display_index(self.cursor)
        if 0 <= di < len(self._display_rows):
            return self._display_rows[di]
        return None

    _scroll_offset: int = 0

    def render(self) -> Text:
        text = Text()

        if self._input_mode:
            label = "rename" if self._input_mode == "rename" else "tag"
            cursor = "_" if self._cursor_visible else " "
            text.append(f"  {label}: {self._input_buffer}{cursor}\n\n", style="bold")

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

        w = self.size.width if self.size.width > 0 else 120

        in_selection = bool(self.selected)
        sel_w = 3 if in_selection else 0

        prefix_w = 1 + sel_w + 2 + 1  # collapse + sel + fav + space
        title_w = max(10, w - prefix_w)

        cursor_display_idx = self._cursor_to_display_index(self.cursor)

        visible_rows: list[tuple[str, str, int]] = []
        # (line_text, style, display_index)

        for di, drow in enumerate(self._display_rows):
            if drow.kind == "bucket":
                visible_rows.append((drow.label[:w], "dim", di))
                continue

            if drow.kind == "session":
                s = drow.session
                assert s is not None
                is_cursor = di == cursor_display_idx
                is_selected = s.session_id in self.selected
                style = "reverse" if is_cursor else ""

                expanded = s.session_id not in self._collapsed
                has_prompts = bool(self._prompts.get(s.session_id))
                if has_prompts:
                    collapse_mark = "▾" if expanded else "▸"
                else:
                    collapse_mark = " "

                sel_mark = ("[x]" if is_selected else "   ") if in_selection else ""
                title = (s.custom_name or strip_markup_tags(strip_system_blocks(s.first_prompt or "")) or "(untitled)")[:title_w]

                fav = " *" if s.is_favorite else "  "

                tags_str = ""
                if w >= 60:
                    tag_rows = self.conn.execute(
                        "SELECT tag FROM tags WHERE session_id = ?", (s.session_id,)
                    ).fetchall()
                    if tag_rows:
                        tags_str = " " + " ".join(f"#{r['tag']}" for r in tag_rows)

                prefix = f"{collapse_mark}{sel_mark}{fav} {title}"
                if tags_str:
                    tags_budget = w - len(prefix)
                    if tags_budget > 3:
                        tags_str = tags_str[:tags_budget]
                    else:
                        tags_str = ""
                line = (prefix + tags_str).ljust(w)[:w]
                visible_rows.append((line, style, di))

            elif drow.kind == "prompt":
                p = drow.prompt
                assert p is not None
                is_cursor = di == cursor_display_idx
                style = "reverse" if is_cursor else ""

                indent = " " * prefix_w
                connector = "│ "
                prompt_w = max(5, w - len(indent) - len(connector))
                prompt_text = strip_system_blocks(p.text)[:prompt_w]
                line = f"{indent}{connector}{prompt_text}"[:w]
                visible_rows.append((line, style, di))

        cursor_row_idx = 0
        for idx, (_, _, di) in enumerate(visible_rows):
            if di == cursor_display_idx:
                cursor_row_idx = idx
                break

        start = max(0, cursor_row_idx - visible_height // 2)
        if start + visible_height > len(visible_rows):
            start = max(0, len(visible_rows) - visible_height)
        start = min(start, cursor_row_idx)
        end = min(start + visible_height, len(visible_rows))

        for row_line, row_style, di in visible_rows[start:end]:
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
    _cursor_visible: bool = True
    _blink_timer: Timer | None = None

    def _start_blink(self) -> None:
        self._cursor_visible = True
        try:
            self._blink_timer = self.set_interval(0.5, self._toggle_cursor)
        except RuntimeError:
            pass

    def _stop_blink(self) -> None:
        if self._blink_timer:
            self._blink_timer.stop()
            self._blink_timer = None
        self._cursor_visible = True

    def _toggle_cursor(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        if getattr(self.app, "_quit_toast_active", False):
            self.app._quit_toast_active = False
            event.stop()
            return

        if self._input_mode:
            self._handle_input_key(event)
            return

        nav_count = self._nav_row_count()
        handled = True
        if event.key in ("up", "k"):
            self.cursor = max(0, self.cursor - 1)
        elif event.key in ("down", "j"):
            self.cursor = min(nav_count - 1, self.cursor + 1)
        elif event.key == "g":
            self.cursor = 0
        elif event.key in ("G", "shift+g"):
            self.cursor = max(0, nav_count - 1)
        elif event.key == "ctrl+u":
            self.cursor = max(0, self.cursor - 10)
        elif event.key == "ctrl+d":
            self.cursor = min(nav_count - 1, self.cursor + 10)
        elif event.key == "e":
            self._toggle_expand()
        elif event.key == "E":
            self._toggle_expand_all()
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
                currently_visible = self.app._preview.display
                self.app._preview_user_override = not currently_visible
                if hasattr(self.app, '_update_preview_layout'):
                    self.app._update_preview_layout()
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
            self._stop_blink()
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
            self._stop_blink()
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
        self._start_blink()
        self._update_footer("rename")
        self.refresh()

    def _start_tag(self):
        s = self.current_session
        if not s:
            return
        self._input_mode = "tag"
        self._input_buffer = ""
        self._start_blink()
        self._update_footer("tag")
        self.refresh()

    def _toggle_expand(self):
        s = self.current_session
        if not s:
            return
        if s.session_id in self._collapsed:
            self._collapsed.discard(s.session_id)
        else:
            self._collapsed.add(s.session_id)
        self._build_display_rows()
        nav_count = self._nav_row_count()
        if self.cursor >= nav_count:
            self.cursor = max(0, nav_count - 1)
        self.refresh()

    def _toggle_expand_all(self):
        if self._collapsed:
            self._collapsed.clear()
        else:
            self._collapsed = {s.session_id for s in self.sessions}
        self._build_display_rows()
        nav_count = self._nav_row_count()
        if self.cursor >= nav_count:
            self.cursor = max(0, nav_count - 1)
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
        from seshi.session_index import reindex_session
        reindex_session(self.conn, s.session_id)
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
