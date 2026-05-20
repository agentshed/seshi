import json
import time

import click

from seshi.cli import main
from seshi.db import open_db
from seshi.cost import estimate_cost, format_usd
from seshi.time_utils import relative_time


@main.command("stats")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def stats(ctx, as_json):
    """Print aggregate session statistics."""
    with open_db() as conn:
        filter_cwd = ctx.obj.get("here_cwd")
        where = "WHERE is_archived = 0"
        params = []
        if filter_cwd:
            where += " AND cwd = ?"
            params.append(filter_cwd)

        totals = conn.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_favorite = 1 THEN 1 ELSE 0 END) as favorites,
                SUM(message_count) as messages,
                SUM(token_count) as tokens,
                MIN(created_at) as oldest,
                MAX(last_activity_at) as newest
            FROM sessions {where}
        """, params).fetchone()

        now = int(time.time())
        week_ago = now - 7 * 86400
        week = conn.execute(f"""
            SELECT COUNT(*) as sessions, SUM(token_count) as tokens
            FROM sessions {where} AND last_activity_at > ?
        """, params + [week_ago]).fetchone()

        model_rows = conn.execute(f"""
            SELECT
                json_extract(env_json, '$.ANTHROPIC_MODEL') as model,
                COUNT(*) as count,
                SUM(token_count) as tokens
            FROM sessions {where} AND env_json IS NOT NULL
            GROUP BY model
            ORDER BY tokens DESC
            LIMIT 8
        """, params).fetchall()

    total_cost = estimate_cost(totals["tokens"] or 0)
    week_cost = estimate_cost(week["tokens"] or 0)

    if as_json:
        data = {
            "total_sessions": totals["total"],
            "favorites": totals["favorites"],
            "total_messages": totals["messages"] or 0,
            "total_tokens": totals["tokens"] or 0,
            "total_cost_usd": round(total_cost, 2),
            "week_sessions": week["sessions"],
            "week_tokens": week["tokens"] or 0,
            "week_cost_usd": round(week_cost, 2),
            "oldest": totals["oldest"],
            "newest": totals["newest"],
            "models": [
                {"model": r["model"] or "unknown", "sessions": r["count"], "tokens": r["tokens"] or 0}
                for r in model_rows
            ],
        }
        click.echo(json.dumps(data, indent=2))
        return

    click.echo(f"sessions: {totals['total']}  favorites: {totals['favorites']}")
    click.echo(f"messages: {totals['messages'] or 0}  tokens: {totals['tokens'] or 0}  cost: {format_usd(total_cost)}")
    click.echo()
    click.echo(f"this week: {week['sessions']} sessions, {week['tokens'] or 0} tokens, {format_usd(week_cost)}")
    click.echo()
    if totals["oldest"]:
        click.echo(f"span: {relative_time(totals['oldest'])} — {relative_time(totals['newest'])}")
    if model_rows:
        click.echo()
        click.echo("by model:")
        for r in model_rows:
            model = r["model"] or "unknown"
            cost = estimate_cost(r["tokens"] or 0, model)
            click.echo(f"  {model:<30} {r['count']:>4} sessions  {format_usd(cost)}")
