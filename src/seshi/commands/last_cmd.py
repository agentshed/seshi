import sys

import click

from seshi.cli import main
from seshi.db import open_db, record_resume
from seshi.models import Session
from seshi.resume import build_resume_line


@main.command("last")
@click.option("--here", is_flag=True, help="Filter to current directory")
@click.pass_context
def last(ctx, here):
    """Resume the most recent session."""
    from seshi.cli import _merge_here
    _merge_here(ctx, here)
    with open_db() as conn:
        sql = "SELECT * FROM sessions WHERE is_archived = 0"
        params = []
        if ctx.obj.get("here_cwd"):
            sql += " AND cwd = ?"
            params.append(ctx.obj["here_cwd"])
        sql += " ORDER BY last_activity_at DESC LIMIT 1"
        row = conn.execute(sql, params).fetchone()

        if not row:
            click.echo("no sessions in registry. Run `seshi scan` to discover existing sessions.", err=True)
            raise SystemExit(1)

        session = Session.from_row(row)
        record_resume(conn, session.session_id)
        line = build_resume_line(session)
        sys.stdout.write(line)
        sys.stdout.flush()
