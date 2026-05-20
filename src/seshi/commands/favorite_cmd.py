import click

from seshi.cli import main
from seshi.db import open_db
from seshi.search import session_resolve


@main.command("favorite")
@click.argument("identifier")
def favorite(identifier):
    """Toggle a session's favorite status."""
    with open_db() as conn:
        session = session_resolve(conn, identifier)
        if not session:
            click.echo(f"session not found: {identifier}", err=True)
            raise SystemExit(1)

        new_val = 0 if session.is_favorite else 1
        conn.execute("UPDATE sessions SET is_favorite = ? WHERE session_id = ?", (new_val, session.session_id))
        conn.commit()
        state = "favorited" if new_val else "unfavorited"
        click.echo(f"{session.session_id[:8]} {state}")
