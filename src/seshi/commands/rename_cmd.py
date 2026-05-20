import click

from seshi.cli import main
from seshi.db import open_db
from seshi.search import session_resolve


@main.command("rename")
@click.argument("identifier")
@click.argument("new_name", required=False)
@click.option("--clear", is_flag=True, help="Remove the custom name")
def rename(identifier, new_name, clear):
    """Set or clear a session's custom name."""
    if not clear and not new_name:
        click.echo("usage: seshi rename <id|name> <new-name> or seshi rename <id|name> --clear", err=True)
        raise SystemExit(2)

    with open_db() as conn:
        session = session_resolve(conn, identifier)
        if not session:
            click.echo(f"session not found: {identifier}", err=True)
            raise SystemExit(1)

        if clear:
            conn.execute("UPDATE sessions SET custom_name = NULL WHERE session_id = ?", (session.session_id,))
            conn.commit()
            click.echo(f"cleared name for {session.session_id[:8]}")
        else:
            existing = conn.execute(
                "SELECT session_id FROM sessions WHERE custom_name = ? COLLATE NOCASE AND session_id != ?",
                (new_name, session.session_id),
            ).fetchone()
            if existing:
                click.echo(f"warning: name '{new_name}' already in use by {existing['session_id'][:8]}", err=True)

            conn.execute("UPDATE sessions SET custom_name = ? WHERE session_id = ?", (new_name, session.session_id))
            conn.commit()
            click.echo(f"renamed {session.session_id[:8]} → {new_name}")
