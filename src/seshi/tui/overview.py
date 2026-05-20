import sqlite3
import time

from textual.widget import Widget
from rich.text import Text

from seshi.cost import estimate_cost, format_usd
from seshi.time_utils import relative_time

SPARK_CHARS = " ▁▂▃▄▅▆▇█"


class OverviewView(Widget):
    DEFAULT_CSS = """
    OverviewView {
        padding: 1 2;
    }
    """

    def __init__(self, conn: sqlite3.Connection, **kwargs):
        super().__init__(**kwargs)
        self.conn = conn

    def render(self) -> Text:
        text = Text()
        now = int(time.time())

        totals = self.conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN is_favorite = 1 THEN 1 ELSE 0 END) as favorites,
                   SUM(message_count) as messages,
                   SUM(token_count) as tokens,
                   MIN(created_at) as oldest,
                   MAX(last_activity_at) as newest
            FROM sessions WHERE is_archived = 0
        """).fetchone()

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
        rows = self.conn.execute("""
            SELECT (? - created_at) / 86400 as day_ago, COUNT(*) as cnt
            FROM sessions WHERE is_archived = 0 AND created_at > ? - 30 * 86400
            GROUP BY day_ago
        """, (now, now)).fetchall()
        for r in rows:
            d = int(r["day_ago"])
            if 0 <= d < 30:
                days[29 - d] = r["cnt"]
        max_val = max(days) if days else 1
        text.append("  ")
        for v in days:
            idx = int((v / max(max_val, 1)) * (len(SPARK_CHARS) - 1))
            text.append(SPARK_CHARS[idx], style="#D97757")
        text.append("\n\n")

        # This week
        week_ago = now - 7 * 86400
        week = self.conn.execute("""
            SELECT COUNT(*) as sessions, SUM(token_count) as tokens
            FROM sessions WHERE is_archived = 0 AND last_activity_at > ?
        """, (week_ago,)).fetchone()
        week_cost = estimate_cost(week["tokens"] or 0)
        text.append("  This week\n", style="bold")
        text.append(f"  {week['sessions']} sessions, {week['tokens'] or 0:,} tokens, {format_usd(week_cost)}\n\n", style="dim")

        # By model
        model_rows = self.conn.execute("""
            SELECT json_extract(env_json, '$.ANTHROPIC_MODEL') as model,
                   COUNT(*) as count, SUM(token_count) as tokens
            FROM sessions WHERE is_archived = 0 AND env_json IS NOT NULL
            GROUP BY model ORDER BY tokens DESC LIMIT 8
        """).fetchall()
        if model_rows:
            text.append("  By model\n", style="bold")
            for r in model_rows:
                model = r["model"] or "unknown"
                cost = estimate_cost(r["tokens"] or 0, model)
                text.append(f"  {model:<30} {r['count']:>4} sessions  {format_usd(cost)}\n", style="dim")
            text.append("\n")

        # Span
        if totals["oldest"]:
            text.append("  Span\n", style="bold")
            text.append(f"  {relative_time(totals['oldest'])} — {relative_time(totals['newest'])}\n", style="dim")

        return text
