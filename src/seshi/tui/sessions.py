import os
import re
import sqlite3
import time
from dataclasses import dataclass

from textual.widget import Widget
from textual.reactive import reactive
from textual import events
from rich.text import Text

from seshi.models import Session, Prompt
from seshi.live import LiveInfo
from seshi.prompt_text import replace_command_tags, strip_markup_tags, strip_system_blocks
from seshi.search import list_sessions, rank_sessions, query_matches_text
from seshi.time_utils import relative_time
from seshi.lang_detect import detect_language
from seshi.db import get_setting, set_setting
from seshi.tui.search_bar import SearchBar, SearchChanged, SCOPES
from seshi.tui.undo import UndoStack, UndoEntry


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
        self._search_expanded: set[str] = set()
        self._manually_expanded: set[str] = set()
        self._display_rows: list[DisplayRow] = []
        self._matching_prompts: set[tuple[str, int]] = set()
        self._tags: dict[str, list[str]] = {}
        self._current_scope: str = "all"
        self._undo = UndoStack()
        self._compact_mode: bool = get_setting(conn, "compact_mode") == "1"
        self._compact_prev_sid: str | None = None
        self._adjusting_compact: bool = False
        self.live_states: dict[str, LiveInfo] = {}
        self._anim_frame: int = 0
        self._load_sessions()

    def on_mount(self) -> None:
        self.set_interval(0.5, self._tick_anim)

    def _tick_anim(self) -> None:
        has_busy = any(
            info.status == "busy"
            for info in self.live_states.values()
        )
        if has_busy:
            self._anim_frame += 1
            self.refresh()

    def _rebuild_and_refresh(self) -> None:
        self._build_display_rows()
        nav_count = self._nav_row_count()
        if self.cursor >= nav_count:
            self.cursor = max(0, nav_count - 1)
        self.refresh()

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

        scope = self._current_scope
        if scope not in SCOPES:
            scope = "all"
        if scope == "favorites":
            sessions = [s for s in sessions if s.is_favorite]
            self.sessions = sessions
        elif scope == "recent":
            cutoff = int(time.time()) - 7 * 86400
            sessions = [s for s in sessions if s.last_activity_at >= cutoff]
            self.sessions = sessions
        elif scope == "project" and self.filter_cwd:
            sessions = [s for s in sessions if s.cwd == self.filter_cwd]
            self.sessions = sessions

        self._load_prompts()
        self._load_tags()

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
                self._search_expanded.add(sid)
        else:
            # Collapse all by default, but preserve manually and search-expanded sessions
            preserved = self._search_expanded | self._manually_expanded
            self._collapsed = {s.session_id for s in self.sessions}
            for sid in preserved:
                self._collapsed.discard(sid)

        if self._compact_mode and not query:
            self._collapsed = {s.session_id for s in self.sessions}
            s = self.current_session or (self.sessions[0] if self.sessions else None)
            if s:
                self._collapsed.discard(s.session_id)
                self._compact_prev_sid = s.session_id
            else:
                self._compact_prev_sid = None

        self._build_display_rows()

        # Position cursor on matching prompt row when search matches
        if query and self._matching_prompts:
            for i, row in enumerate(self._display_rows):
                if row.kind == "prompt" and row.session and row.prompt:
                    if (row.session.session_id, row.prompt.prompt_index) in self._matching_prompts:
                        nav_idx = sum(1 for r in self._display_rows[:i] if r.kind != "bucket")
                        self.cursor = nav_idx
                        break

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

    def _load_tags(self):
        self._tags = {}
        if not self._all_sessions:
            return
        ids = [s.session_id for s in self._all_sessions]
        placeholders = ",".join("?" * len(ids))
        try:
            rows = self.conn.execute(
                f"SELECT session_id, tag FROM tags WHERE session_id IN ({placeholders})",
                ids,
            ).fetchall()
            for row in rows:
                sid = row["session_id"]
                if sid not in self._tags:
                    self._tags[sid] = []
                self._tags[sid].append(row["tag"])
        except Exception:
            pass

    def _build_display_rows(self):
        rows: list[DisplayRow] = []
        home = os.path.expanduser("~")

        live_sids = set(self.live_states.keys())

        live_sessions: list[Session] = []
        remaining: list[Session] = []
        for s in self.sessions:
            if s.session_id in live_sids:
                live_sessions.append(s)
            else:
                remaining.append(s)

        tracked_sids = {s.session_id for s in self.sessions}
        for sid, info in self.live_states.items():
            if sid not in tracked_sids:
                live_sessions.append(Session(
                    session_id=sid,
                    cwd=info.cwd,
                    launch_argv_json="[]",
                    env_json=None,
                    git_branch=None,
                    git_sha=None,
                    first_prompt=None,
                    custom_name=info.name,
                    ai_title=None,
                    is_favorite=0,
                    is_archived=0,
                    is_backfilled=0,
                    message_count=0,
                    token_count=0,
                    status=None,
                    created_at=0,
                    last_activity_at=0,
                    origin_host=None,
                    schema_version=0,
                ))

        status_order = {"needs_input": 0, "busy": 1, "idle": 2}
        live_sessions.sort(
            key=lambda s: status_order.get(
                self.live_states[s.session_id].status
                if s.session_id in self.live_states else "idle", 3
            )
        )

        if live_sessions:
            rows.append(DisplayRow(kind="bucket", label=f"  ── ● {len(live_sessions)} live ──"))
            for s in live_sessions:
                rows.append(DisplayRow(kind="session", session=s))
                if s.session_id not in self._collapsed:
                    for p in self._prompts.get(s.session_id, []):
                        if strip_system_blocks(replace_command_tags(p.text)):
                            rows.append(DisplayRow(kind="prompt", session=s, prompt=p))

        favorites = [s for s in remaining if s.is_favorite]
        non_favorites = [s for s in remaining if not s.is_favorite]

        if favorites:
            rows.append(DisplayRow(kind="bucket", label="  ── ★ favorites ──"))
            for s in favorites:
                rows.append(DisplayRow(kind="session", session=s))
                if s.session_id not in self._collapsed:
                    for p in self._prompts.get(s.session_id, []):
                        if strip_system_blocks(replace_command_tags(p.text)):
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
                        if strip_system_blocks(replace_command_tags(p.text)):
                            rows.append(DisplayRow(kind="prompt", session=s, prompt=p))

        self._display_rows = rows

    def filter(self, query: str, scope: str = "all"):
        text, tags = _parse_search(query)
        self._current_query = text
        self._current_tags = tags if tags else None
        self._current_scope = scope
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
        if self._compact_mode and not self._adjusting_compact:
            s = self.current_session
            new_sid = s.session_id if s else None
            if new_sid != self._compact_prev_sid:
                if self._compact_prev_sid:
                    self._collapsed.add(self._compact_prev_sid)
                if new_sid:
                    self._collapsed.discard(new_sid)
                self._compact_prev_sid = new_sid
                self._build_display_rows()
                nav_count = self._nav_row_count()
                if self.cursor >= nav_count:
                    self._adjusting_compact = True
                    self.cursor = max(0, nav_count - 1)
                    self._adjusting_compact = False
        try:
            if hasattr(self.app, '_preview'):
                s = self.current_session
                self.app._preview.session = s
                di = self._cursor_to_display_index(cursor)
                row = self._display_rows[di] if 0 <= di < len(self._display_rows) else None
                if hasattr(self.app._preview, 'focus_prompt_index'):
                    self.app._preview.focus_prompt_index = row.prompt.prompt_index if row and row.prompt else None
                live = self.live_states.get(s.session_id) if s else None
                if hasattr(self.app._preview, 'live_state'):
                    self.app._preview.live_state = live
        except Exception:
            pass
        try:
            if hasattr(self.app, '_update_footer_live'):
                self.app._update_footer_live()
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

        has_untracked_live = bool(self.live_states) and any(
            sid not in {s.session_id for s in self.sessions}
            for sid in self.live_states
        )
        if not self.sessions and not has_untracked_live:
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

        has_live = bool(self.live_states)
        state_w = 1 if has_live else 0
        prefix_w = 1 + state_w + sel_w + 2 + 1  # collapse + state + sel + fav + space
        title_w = max(10, w - prefix_w)

        cursor_display_idx = self._cursor_to_display_index(self.cursor)

        # (line_text, style, display_index, live_info_or_none)
        visible_rows: list[tuple[str, str, int, object]] = []

        home = os.path.expanduser("~")

        for di, drow in enumerate(self._display_rows):
            if drow.kind == "bucket":
                visible_rows.append((drow.label[:w], "dim", di, None))
                continue

            if drow.kind == "session":
                s = drow.session
                assert s is not None
                is_cursor = di == cursor_display_idx
                is_selected = s.session_id in self.selected
                style = "reverse" if is_cursor else ""

                live = self.live_states.get(s.session_id)

                expanded = s.session_id not in self._collapsed
                has_prompts = bool(self._prompts.get(s.session_id))
                if has_prompts:
                    collapse_mark = "▾" if expanded else "▸"
                elif live:
                    collapse_mark = " "
                else:
                    collapse_mark = "─"

                if has_live:
                    if live:
                        if live.status == "busy":
                            state_icon = "✽" if self._anim_frame % 2 == 0 else "✻"
                        elif live.status == "needs_input":
                            state_icon = "✻"
                        else:
                            state_icon = "✻"
                    else:
                        state_icon = " "
                else:
                    state_icon = ""

                sel_mark = ("[x]" if is_selected else "   ") if in_selection else ""
                title = (s.custom_name or s.ai_title or strip_markup_tags(strip_system_blocks(s.first_prompt or "")) or "(untitled)")

                fav = " *" if s.is_favorite else "  "

                tags_str = ""
                if w >= 60:
                    session_tags = self._tags.get(s.session_id, [])
                    if session_tags:
                        tags_str = " " + " ".join(f"#{t}" for t in session_tags)

                right_text = ""
                if live and w > 80:
                    short_cwd = s.cwd
                    if short_cwd.startswith(home + "/"):
                        short_cwd = "~/" + short_cwd[len(home) + 1:].split("/")[-1]
                    elif "/" in short_cwd:
                        short_cwd = short_cwd.split("/")[-1]
                    if live.detail:
                        right_text = f" {short_cwd} · {live.detail}"
                    else:
                        right_text = f" {short_cwd}"

                prefix = f"{collapse_mark}{state_icon}{sel_mark}{fav} "
                avail_title = max(10, w - len(prefix) - len(tags_str) - len(right_text))
                title = title[:avail_title]
                left = prefix + title + tags_str
                if right_text:
                    gap = w - len(left) - len(right_text)
                    if gap > 0:
                        line = left + " " * gap + right_text
                    else:
                        line = left.ljust(w)
                else:
                    line = left.ljust(w)
                line = line[:w]
                visible_rows.append((line, style, di, live))

            elif drow.kind == "prompt":
                p = drow.prompt
                assert p is not None
                is_cursor = di == cursor_display_idx
                style = "reverse" if is_cursor else ""

                indent = " " * prefix_w
                connector = "│ "
                prompt_w = max(5, w - len(indent) - len(connector))
                prompt_text = strip_system_blocks(replace_command_tags(p.text))[:prompt_w]
                line = f"{indent}{connector}{prompt_text}"[:w]
                visible_rows.append((line, style, di, None))

        cursor_row_idx = 0
        for idx, (_, _, di, _) in enumerate(visible_rows):
            if di == cursor_display_idx:
                cursor_row_idx = idx
                break

        start = max(0, cursor_row_idx - visible_height // 2)
        if start + visible_height > len(visible_rows):
            start = max(0, len(visible_rows) - visible_height)
        start = min(start, cursor_row_idx)
        end = min(start + visible_height, len(visible_rows))

        try:
            accent = self.app._palette.accent
        except Exception:
            accent = "#E08A5E"

        for row_line, row_style, di, live in visible_rows[start:end]:
            if live and state_w:
                line_text = Text()
                line_text.append(row_line[0], style=row_style)
                icon_char = row_line[1]
                if live.status == "busy":
                    icon_style = accent
                elif live.status == "needs_input":
                    icon_style = "yellow"
                else:
                    icon_style = "dim"
                if row_style == "reverse":
                    icon_style = f"reverse {icon_style}"
                line_text.append(icon_char, style=icon_style)
                line_text.append(row_line[2:] + "\n", style=row_style)
                if self._current_query:
                    line_text.highlight_words([self._current_query], style="bold underline", case_sensitive=False)
                text.append_text(line_text)
            elif self._current_query and row_style != "dim":
                line_text = Text(row_line + "\n", style=row_style)
                line_text.highlight_words([self._current_query], style="bold underline", case_sensitive=False)
                text.append_text(line_text)
            else:
                text.append(row_line + "\n", style=row_style)

        remaining = visible_height - (end - start)
        for _ in range(remaining):
            text.append("~\n", style="dim")

        return text

    def _notify(self, message: str, **kwargs) -> None:
        try:
            self.app.notify(message, **kwargs)
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:
        if getattr(self.app, "_quit_toast_active", False):
            self.app._quit_toast_active = False
            event.stop()
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
            self._cycle_sort()
        elif event.key == "H":
            self._toggle_hide_missing()
        elif event.key == "S":
            self._toggle_hide_stale()
        elif event.key == "z":
            self._undo_last()
        elif event.key == "c":
            self._toggle_compact_mode()
        elif event.key == "P":
            self._filter_to_current_project()
        elif event.key == "p":
            self._cycle_preview()
        elif event.key == "slash":
            search = self.app.query_one(SearchBar)
            search.active = True
            search.focus()
        elif event.key == "escape":
            pass  # handled by app-level action_back_or_quit
        elif event.key == "enter":
            s = self.current_session
            if s:
                live = self.live_states.get(s.session_id)
                if live and live.kind == "background":
                    self.app.chosen_action = "attach"
                else:
                    self.app.chosen_action = "resume"
                self.app.chosen_session = s
                self.app.exit()
                return
        else:
            if event.is_printable and event.character:
                search = self.app.query_one(SearchBar)
                search.active = True
                search.search_text += event.character
                search.post_message(SearchChanged(search.search_text, search.scope))
            elif event.key == "backspace":
                search = self.app.query_one(SearchBar)
                if search.search_text:
                    search.search_text = search.search_text[:-1]
                    search.post_message(SearchChanged(search.search_text, search.scope))
            else:
                handled = False

        if handled:
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
        search = self.app.query_one(SearchBar)
        search.enter_mode("rename", prefill=s.custom_name or "")
        self._update_footer("rename")

    def _start_tag(self):
        s = self.current_session
        if not s:
            return
        search = self.app.query_one(SearchBar)
        search.enter_mode("tag")
        self._update_footer("tag")

    def _toggle_expand(self):
        s = self.current_session
        if not s:
            return
        if not self._prompts.get(s.session_id):
            return
        if s.session_id in self._collapsed:
            self._collapsed.discard(s.session_id)
            self._manually_expanded.add(s.session_id)
        else:
            self._collapsed.add(s.session_id)
            self._search_expanded.discard(s.session_id)
            self._manually_expanded.discard(s.session_id)
        self._build_display_rows()
        nav_count = self._nav_row_count()
        if self.cursor >= nav_count:
            self.cursor = max(0, nav_count - 1)
        self.refresh()

    def _toggle_expand_all(self):
        if self._collapsed:
            self._collapsed.clear()
            self._search_expanded.clear()
            self._manually_expanded.clear()
        else:
            self._collapsed = {s.session_id for s in self.sessions}
            self._search_expanded.clear()
            self._manually_expanded.clear()
        self._build_display_rows()
        nav_count = self._nav_row_count()
        if self.cursor >= nav_count:
            self.cursor = max(0, nav_count - 1)
        self.refresh()

    def _toggle_compact_mode(self):
        self._compact_mode = not self._compact_mode
        set_setting(self.conn, "compact_mode", "1" if self._compact_mode else "0")
        self._search_expanded.clear()
        self._manually_expanded.clear()
        if self._compact_mode:
            self._collapsed = {s.session_id for s in self.sessions}
            s = self.current_session
            if s:
                self._collapsed.discard(s.session_id)
                self._compact_prev_sid = s.session_id
            else:
                self._compact_prev_sid = None
        else:
            self._collapsed = {s.session_id for s in self.sessions}
            self._compact_prev_sid = None
        self._build_display_rows()
        nav_count = self._nav_row_count()
        if self.cursor >= nav_count:
            self.cursor = max(0, nav_count - 1)
        self.refresh()

    def _filter_to_current_project(self):
        s = self.current_session
        if not s:
            return
        self.filter_cwd = s.cwd
        self._load_sessions(query=self._current_query, tags=self._current_tags)
        try:
            self.app._update_counts()
            self.app._update_breadcrumb()
        except Exception:
            pass

    def _reload_with_current_filter(self):
        self._load_sessions(query=self._current_query, tags=self._current_tags)
        try:
            self.app._update_counts()
        except Exception:
            pass

    def _cycle_sort(self):
        modes = ["frecency", "recency", "frequency"]
        idx = modes.index(self.sort_mode) if self.sort_mode in modes else 0
        self.sort_mode = modes[(idx + 1) % len(modes)]
        set_setting(self.conn, "sort_mode", self.sort_mode)
        self._reload_with_current_filter()

    def _toggle_hide_missing(self):
        current = get_setting(self.conn, "hide_missing_dirs")
        new_val = "0" if current == "1" else "1"
        set_setting(self.conn, "hide_missing_dirs", new_val)
        self._reload_with_current_filter()

    def _toggle_hide_stale(self):
        current = get_setting(self.conn, "hide_stale_sessions")
        new_val = "0" if current == "1" else "1"
        set_setting(self.conn, "hide_stale_sessions", new_val)
        self._reload_with_current_filter()

    def _cycle_preview(self):
        if hasattr(self.app, '_preview'):
            from seshi.tui.app import SeshiApp
            modes = SeshiApp.PREVIEW_MODES
            current = getattr(self.app, '_preview_mode', 'normal')
            idx = modes.index(current) if current in modes else 0
            self.app._preview_mode = modes[(idx + 1) % len(modes)]
            if hasattr(self.app, '_update_preview_layout'):
                self.app._update_preview_layout()

    def _apply_rename_text(self, text: str):
        s = self.current_session
        if not s:
            return
        old_name = s.custom_name
        name = text.strip() or None
        self.conn.execute("UPDATE sessions SET custom_name = ? WHERE session_id = ?", (name, s.session_id))
        self.conn.commit()
        display = name or "(untitled)"
        self._undo.push(UndoEntry(
            action="rename",
            description=f"Renamed to {display}",
            sql_statements=[
                ("UPDATE sessions SET custom_name = ? WHERE session_id = ?", (old_name, s.session_id)),
            ],
            session_ids=[s.session_id],
        ))
        self._notify(f"Renamed to '{display}'", severity="information", timeout=2)
        from seshi.session_index import reindex_session
        reindex_session(self.conn, s.session_id)
        self._reload_with_current_filter()

    def _apply_tag_text(self, text: str):
        tag = text.strip()
        if not tag or not re.match(r"^[\w\-]+$", tag):
            return
        targets = list(self.selected) if self.selected else [self.current_session.session_id] if self.current_session else []
        undo_stmts: list[tuple[str, tuple]] = []
        added = 0
        removed = 0
        for sid in targets:
            existing = self.conn.execute("SELECT 1 FROM tags WHERE session_id = ? AND tag = ?", (sid, tag)).fetchone()
            if existing:
                self.conn.execute("DELETE FROM tags WHERE session_id = ? AND tag = ?", (sid, tag))
                undo_stmts.append(("INSERT OR IGNORE INTO tags (session_id, tag) VALUES (?, ?)", (sid, tag)))
                removed += 1
            else:
                self.conn.execute("INSERT INTO tags (session_id, tag) VALUES (?, ?)", (sid, tag))
                undo_stmts.append(("DELETE FROM tags WHERE session_id = ? AND tag = ?", (sid, tag)))
                added += 1
        self.conn.commit()
        if added:
            self._notify(f"Tagged #{tag}" + (f" on {added} sessions" if added > 1 else ""))
        elif removed:
            self._notify(f"Untagged #{tag}" + (f" from {removed} sessions" if removed > 1 else ""))
        self._undo.push(UndoEntry(
            action="tag",
            description=f"Tag #{tag}",
            sql_statements=undo_stmts,
            session_ids=targets,
        ))
        self._reload_with_current_filter()

    def _toggle_favorite(self):
        s = self.current_session
        if not s:
            return
        targets = list(self.selected) if self.selected else [s.session_id]
        undo_stmts: list[tuple[str, tuple]] = []
        for sid in targets:
            row = self.conn.execute("SELECT is_favorite FROM sessions WHERE session_id = ?", (sid,)).fetchone()
            old_val = row["is_favorite"] if row else 0
            self.conn.execute(
                "UPDATE sessions SET is_favorite = CASE WHEN is_favorite = 1 THEN 0 ELSE 1 END WHERE session_id = ?",
                (sid,),
            )
            undo_stmts.append(("UPDATE sessions SET is_favorite = ? WHERE session_id = ?", (old_val, sid)))
        self.conn.commit()
        if len(targets) == 1:
            new_state = 0 if s.is_favorite else 1
            label = "Favorited" if new_state else "Unfavorited"
        else:
            label = f"Toggled favorite on {len(targets)} sessions"
        self._notify(label, severity="information", timeout=2)
        self._undo.push(UndoEntry(
            action="favorite",
            description=label,
            sql_statements=undo_stmts,
            session_ids=targets,
        ))
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
        undo_stmts: list[tuple[str, tuple]] = []
        first_was_archived = None
        for sid in targets:
            row = self.conn.execute("SELECT is_archived FROM sessions WHERE session_id = ?", (sid,)).fetchone()
            old_val = row["is_archived"] if row else 0
            if first_was_archived is None:
                first_was_archived = old_val
            self.conn.execute(
                "UPDATE sessions SET is_archived = CASE WHEN is_archived = 1 THEN 0 ELSE 1 END WHERE session_id = ?",
                (sid,),
            )
            undo_stmts.append(("UPDATE sessions SET is_archived = ? WHERE session_id = ?", (old_val, sid)))
        self.conn.commit()
        count = len(targets)
        verb = "Unarchived" if first_was_archived else "Archived"
        label = f"{verb} {count} session{'s' if count > 1 else ''}"
        self._notify(label, severity="information", timeout=2)
        self._undo.push(UndoEntry(
            action="archive",
            description=label,
            sql_statements=undo_stmts,
            session_ids=targets,
        ))
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
        undo_stmts: list[tuple[str, tuple]] = []
        for sid in targets:
            row = self.conn.execute("SELECT * FROM sessions WHERE session_id = ?", (sid,)).fetchone()
            if row:
                cols = row.keys()
                vals = tuple(row[c] for c in cols)
                placeholders = ",".join("?" * len(cols))
                col_names = ",".join(cols)
                undo_stmts.append((f"INSERT OR IGNORE INTO sessions ({col_names}) VALUES ({placeholders})", vals))
            tag_rows = self.conn.execute("SELECT session_id, tag FROM tags WHERE session_id = ?", (sid,)).fetchall()
            for tr in tag_rows:
                undo_stmts.append(("INSERT OR IGNORE INTO tags (session_id, tag) VALUES (?, ?)", (tr["session_id"], tr["tag"])))
            prompt_rows = self.conn.execute(
                "SELECT session_id, prompt_index, text, timestamp_epoch FROM prompts WHERE session_id = ?", (sid,)
            ).fetchall()
            for pr in prompt_rows:
                undo_stmts.append((
                    "INSERT OR IGNORE INTO prompts (session_id, prompt_index, text, timestamp_epoch) VALUES (?, ?, ?, ?)",
                    (pr["session_id"], pr["prompt_index"], pr["text"], pr["timestamp_epoch"]),
                ))
            self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
        self.conn.commit()
        count = len(targets)
        label = f"Deleted {count} session{'s' if count > 1 else ''}"
        self._notify(label, severity="warning", timeout=2)
        self._undo.push(UndoEntry(
            action="delete",
            description=label,
            sql_statements=undo_stmts,
            session_ids=targets,
        ))
        self.selected.clear()
        self._reload_with_current_filter()


    def _undo_last(self):
        entry = self._undo.pop()
        if not entry:
            self._notify("Nothing to undo", severity="warning")
            return
        for sql, params in entry.sql_statements:
            self.conn.execute(sql, params)
        self.conn.commit()
        if entry.action in ("rename", "delete"):
            from seshi.session_index import reindex_session
            from seshi.transcript_index import index_session as reindex_transcript
            for sid in entry.session_ids:
                reindex_session(self.conn, sid)
                if entry.action == "delete":
                    reindex_transcript(self.conn, sid)
        self._notify(f"Undo: {entry.description}")
        self._reload_with_current_filter()


def _parse_search(query: str) -> tuple[str, list[str]]:
    parts = query.split()
    tags = [p[1:] for p in parts if p.startswith("#")]
    text = " ".join(p for p in parts if not p.startswith("#"))
    return text, tags
