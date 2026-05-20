import os
import sys

import click

from seshi.cli import main
from seshi.db import open_db
from seshi.search import session_resolve


@main.command("delete")
@click.argument("identifier")
@click.option("--force", is_flag=True, help="Skip confirmation")
def delete(identifier, force):
    """Delete a session from the registry."""
    with open_db() as conn:
        session = session_resolve(conn, identifier)
        if not session:
            click.echo(f"session not found: {identifier}", err=True)
            raise SystemExit(1)

        name = session.custom_name or session.first_prompt or session.session_id[:8]

        if not force:
            try:
                tty = open("/dev/tty", "r")
                tty_out = open("/dev/tty", "w")
                tty_out.write(f"delete session '{name}'? [y/N] ")
                tty_out.flush()
                answer = tty.readline().strip().lower()
                tty.close()
                tty_out.close()
                if answer not in ("y", "yes"):
                    raise SystemExit(0)
            except OSError:
                click.echo("use --force to delete without confirmation, or run interactively.", err=True)
                raise SystemExit(1)

        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session.session_id,))
        conn.commit()
        click.echo(f"deleted {session.session_id[:8]}")
