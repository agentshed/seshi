import sys

import click

from seshi.cli import main
from seshi.db import open_db
from seshi.resume import build_resume_line
from seshi.search import session_resolve, rank_sessions


@main.command("resume")
@click.argument("query", nargs=-1, required=True)
@click.pass_context
def resume(ctx, query):
    """Resume a session by ID, name, or fuzzy query."""
    query_str = " ".join(query)
    with open_db() as conn:
        session = session_resolve(conn, query_str)
        if session:
            line = build_resume_line(session)
            sys.stdout.write(line)
            sys.stdout.flush()
            return

        results = rank_sessions(conn, query_str, filter_cwd=ctx.obj.get("here_cwd"))
        if not results:
            click.echo(f"session not found: {query_str}", err=True)
            raise SystemExit(1)

        top_score = results[0][1]
        second_score = results[1][1] if len(results) > 1 else 0

        if second_score == 0 or top_score >= second_score * 1.4:
            session = results[0][0]
            name = session.custom_name or session.first_prompt or session.session_id[:8]
            click.echo(f"match: {name} ({session.cwd})", err=True)
            click.echo("press Enter to resume, or Ctrl-C to cancel", err=True)
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                raise SystemExit(0)
            line = build_resume_line(session)
            sys.stdout.write(line)
            sys.stdout.flush()
        else:
            click.echo(f"ambiguous query: {query_str}", err=True)
            click.echo("top matches:", err=True)
            for session, score in results[:5]:
                name = session.custom_name or session.first_prompt or session.session_id[:8]
                click.echo(f"  {name} ({session.cwd})", err=True)
            raise SystemExit(1)
