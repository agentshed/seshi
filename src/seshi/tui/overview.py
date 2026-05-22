import math
import re
import sqlite3
import time

from textual.widget import Widget
from textual import events
from rich.text import Text

from seshi.cost import estimate_cost, format_usd
from seshi.db import get_setting
from seshi.time_utils import relative_time

SPARK_CHARS = " ▁▂▃▄▅▆▇█"

_CTX_SUFFIX_RE = re.compile(r"\[[\d]+[kmKM]\]$")


class OverviewView(Widget):
    DEFAULT_CSS = """
    OverviewView {
        padding: 1 2;
    }
    """

    can_focus = True
    _scroll_offset: int = 0

    def __init__(self, conn: sqlite3.Connection, **kwargs):
        super().__init__(**kwargs)
        self.conn = conn

    def _build_filter(self) -> tuple[str, list]:
        """Build extra WHERE clause and params to exclude stale/missing sessions."""
        hide_stale = get_setting(self.conn, "hide_stale_sessions") == "1"
        hide_missing = get_setting(self.conn, "hide_missing_dirs") == "1"
        if not hide_stale and not hide_missing:
            return "", []

        rows = self.conn.execute(
            "SELECT session_id, cwd FROM sessions WHERE is_archived = 0"
        ).fetchall()

        excluded: set[str] = set()
        if hide_stale:
            from seshi.transcript import get_existing_session_ids
            existing = get_existing_session_ids()
            for r in rows:
                if r["session_id"] not in existing:
                    excluded.add(r["session_id"])
        if hide_missing:
            import os
            for r in rows:
                if not os.path.isdir(r["cwd"]):
                    excluded.add(r["session_id"])

        if not excluded:
            return "", []
        placeholders = ",".join("?" * len(excluded))
        return f" AND session_id NOT IN ({placeholders})", list(excluded)

    def render(self) -> Text:
        text = Text()
        now = int(time.time())
        extra_where, extra_params = self._build_filter()

        totals = self.conn.execute(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN is_favorite = 1 THEN 1 ELSE 0 END) as favorites,
                   SUM(message_count) as messages,
                   SUM(token_count) as tokens,
                   MIN(created_at) as oldest,
                   MAX(last_activity_at) as newest
            FROM sessions WHERE is_archived = 0{extra_where}
        """, extra_params).fetchone()

        total_tokens = totals["tokens"] or 0
        total_cost = estimate_cost(total_tokens)

        text.append("  Totals\n", style="bold")
        text.append(f"  sessions: {totals['total']}    ", style="dim")
        text.append(f"favorites: {totals['favorites']}    ", style="dim")
        text.append(f"messages: {totals['messages'] or 0}    ", style="dim")
        text.append(f"tokens: {total_tokens:,}    ", style="dim")
        text.append(f"cost: {format_usd(total_cost)}\n\n", style="dim")

        # 30-day sparkline
        text.append("  Last 30 days\n", style="bold")
        days = [0] * 30
        rows = self.conn.execute(f"""
            SELECT (? - created_at) / 86400 as day_ago, COUNT(*) as cnt
            FROM sessions WHERE is_archived = 0 AND created_at > ? - 30 * 86400{extra_where}
            GROUP BY day_ago
        """, [now, now] + extra_params).fetchall()
        for r in rows:
            d = int(r["day_ago"])
            if 0 <= d < 30:
                days[29 - d] = r["cnt"]
        max_val = max(days) if days else 1
        text.append("  ")
        log_max = math.log1p(max_val)
        for v in days:
            if v == 0:
                idx = 0
            else:
                idx = int((math.log1p(v) / max(log_max, 1)) * (len(SPARK_CHARS) - 1))
            text.append(SPARK_CHARS[idx], style="#D97757")
        text.append("\n\n")

        # This week
        week_ago = now - 7 * 86400
        week = self.conn.execute(f"""
            SELECT COUNT(*) as sessions, SUM(token_count) as tokens
            FROM sessions WHERE is_archived = 0 AND last_activity_at > ?{extra_where}
        """, [week_ago] + extra_params).fetchone()
        week_cost = estimate_cost(week["tokens"] or 0)
        text.append("  This week\n", style="bold")
        text.append(f"  {week['sessions']} sessions, {week['tokens'] or 0:,} tokens, {format_usd(week_cost)}\n\n", style="dim")

        # By model
        model_rows = self.conn.execute(f"""
            SELECT json_extract(env_json, '$.ANTHROPIC_MODEL') as model,
                   COUNT(*) as count, SUM(token_count) as tokens
            FROM sessions WHERE is_archived = 0 AND env_json IS NOT NULL{extra_where}
            GROUP BY model ORDER BY tokens DESC LIMIT 8
        """, extra_params).fetchall()
        if model_rows:
            text.append("  By model\n", style="bold")
            for r in model_rows:
                model = _CTX_SUFFIX_RE.sub("", r["model"] or "unknown")
                cost = estimate_cost(r["tokens"] or 0, model)
                text.append(f"  {model:<30} {r['count']:>4} sessions  {format_usd(cost)}\n", style="dim")
            text.append("\n")

        # Span
        if totals["oldest"]:
            text.append("  Span\n", style="bold")
            text.append(f"  {relative_time(totals['oldest'])} — {relative_time(totals['newest'])}\n", style="dim")

        return text

    def on_key(self, event: events.Key) -> None:
        if event.key in ("down", "j"):
            self._scroll_offset = min(self._scroll_offset + 1, 20)
            self.scroll_relative(y=1)
            self.refresh()
            event.stop()
        elif event.key in ("up", "k"):
            self._scroll_offset = max(self._scroll_offset - 1, 0)
            self.scroll_relative(y=-1)
            self.refresh()
            event.stop()
