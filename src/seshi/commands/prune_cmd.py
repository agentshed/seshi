import time

import click

from seshi.cli import main
from seshi.db import open_db, get_setting


@main.command("prune")
@click.option("--dry-run", is_flag=True, help="Preview without deleting")
@click.option("--days", type=int, help="Override prune_days setting")
def prune(dry_run, days):
    """Delete old sessions from registry."""
    with open_db() as conn:
        if days is None:
            days = int(get_setting(conn, "prune_days") or "0")
        if days == 0:
            click.echo("prune_days = 0 (disabled).")
            return

        cutoff = int(time.time()) - days * 86400
        rows = conn.execute(
            """SELECT session_id, custom_name, first_prompt, last_activity_at
            FROM sessions
            WHERE last_activity_at < ? AND is_favorite = 0 AND custom_name IS NULL""",
            (cutoff,),
        ).fetchall()

        if not rows:
            click.echo("no sessions to prune.")
            return

        if dry_run:
            click.echo(f"would prune {len(rows)} session{'s' if len(rows) != 1 else ''}:")
            for r in rows:
                label = r["first_prompt"] or r["session_id"][:8]
                click.echo(f"  {label}")
            return

        conn.execute(
            "DELETE FROM sessions WHERE last_activity_at < ? AND is_favorite = 0 AND custom_name IS NULL",
            (cutoff,),
        )
        conn.commit()
        click.echo(f"pruned {len(rows)} session{'s' if len(rows) != 1 else ''}.")
