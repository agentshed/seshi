import click

from seshi.cli import main
from seshi.db import open_db
from seshi.search import session_resolve


@main.command("archive")
@click.argument("identifier")
def archive(identifier):
    """Toggle a session's archived status."""
    with open_db() as conn:
        session = session_resolve(conn, identifier)
        if not session:
            click.echo(f"session not found: {identifier}", err=True)
            raise SystemExit(1)

        new_val = 0 if session.is_archived else 1
        conn.execute("UPDATE sessions SET is_archived = ? WHERE session_id = ?", (new_val, session.session_id))
        conn.commit()
        state = "archived" if new_val else "unarchived"
        click.echo(f"{session.session_id[:8]} {state}")
