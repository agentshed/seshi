import re

import click

from seshi.cli import main
from seshi.db import open_db
from seshi.search import session_resolve

TAG_RE = re.compile(r"^[\w\-]+$")


@main.command("tag")
@click.argument("identifier")
@click.argument("tag_name")
@click.option("--remove", is_flag=True, help="Remove the tag")
def tag(identifier, tag_name, remove):
    """Add or remove a tag on a session."""
    if not TAG_RE.match(tag_name):
        click.echo(f"invalid tag: '{tag_name}'. Only word characters and hyphens allowed.", err=True)
        raise SystemExit(2)

    with open_db() as conn:
        session = session_resolve(conn, identifier)
        if not session:
            click.echo(f"session not found: {identifier}", err=True)
            raise SystemExit(1)

        if remove:
            result = conn.execute(
                "DELETE FROM tags WHERE session_id = ? AND tag = ?",
                (session.session_id, tag_name),
            )
            conn.commit()
            if result.rowcount == 0:
                click.echo(f"tag '{tag_name}' not found on {session.session_id[:8]}")
            else:
                click.echo(f"removed #{tag_name} from {session.session_id[:8]}")
        else:
            existing = conn.execute(
                "SELECT 1 FROM tags WHERE session_id = ? AND tag = ?",
                (session.session_id, tag_name),
            ).fetchone()
            if existing:
                click.echo(f"tag '{tag_name}' already on {session.session_id[:8]}")
            else:
                conn.execute(
                    "INSERT INTO tags (session_id, tag) VALUES (?, ?)",
                    (session.session_id, tag_name),
                )
                conn.commit()
                click.echo(f"added #{tag_name} to {session.session_id[:8]}")
