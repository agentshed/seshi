import json
import sys
from datetime import datetime, timezone

import click

from seshi.cli import main
from seshi.db import open_db
from seshi.search import session_resolve
from seshi.transcript import find_transcript_path, extract_messages, parse_transcript
from seshi.time_utils import relative_time


@main.command("export")
@click.argument("identifier")
@click.option("--md", "fmt", flag_value="md", help="Markdown output")
@click.option("--json", "fmt", flag_value="json", help="JSON output")
def export_cmd(identifier, fmt):
    """Dump a session transcript to stdout."""
    if "/" in identifier or ".." in identifier:
        click.echo("invalid session id", err=True)
        raise SystemExit(2)

    with open_db() as conn:
        session = session_resolve(conn, identifier)
    if not session:
        click.echo(f"session not found: {identifier}", err=True)
        raise SystemExit(1)

    path = find_transcript_path(session.session_id)
    if not path:
        click.echo(f"no transcript found for session {identifier}", err=True)
        raise SystemExit(1)

    if fmt == "md":
        _export_markdown(session, path)
    elif fmt == "json":
        _export_json(session, path)
    else:
        sys.stdout.write(path.read_text())


def _export_markdown(session, path):
    title = session.custom_name or session.first_prompt or session.session_id
    dt = datetime.fromtimestamp(session.created_at, tz=timezone.utc)
    date_str = dt.strftime("%Y-%m-%d")

    click.echo(f"# {title}\n")
    click.echo(f"`{session.cwd}` · {date_str} · {session.message_count} messages · {session.token_count} tokens\n")
    click.echo("---\n")

    messages = extract_messages(path)
    for msg in messages:
        click.echo(f"### {msg.role}\n")
        click.echo(f"{msg.text}\n")
        click.echo("---\n")


def _export_json(session, path):
    messages = extract_messages(path)
    data = {
        "session_id": session.session_id,
        "cwd": session.cwd,
        "custom_name": session.custom_name,
        "first_prompt": session.first_prompt,
        "message_count": session.message_count,
        "token_count": session.token_count,
        "created_at": session.created_at,
        "messages": [{"role": m.role, "text": m.text, "timestamp": m.timestamp} for m in messages],
    }
    click.echo(json.dumps(data, indent=2))
