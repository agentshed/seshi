import re
import shutil
import subprocess

import click

from seshi.cli import main
from seshi.db import open_db
from seshi.search import session_resolve
from seshi.transcript import find_transcript_path, extract_messages

VALID_NAME_RE = re.compile(r"^[a-z][a-z0-9-]+$")


@main.command("auto-name")
@click.argument("identifier", required=False)
@click.option("--all", "all_unnamed", is_flag=True, help="Name all unnamed sessions")
@click.option("--limit", type=int, default=10, help="Max sessions for --all")
@click.pass_context
def auto_name(ctx, identifier, all_unnamed, limit):
    """Generate a name for a session via Claude."""
    if not shutil.which("claude"):
        click.echo("error: 'claude' not found on PATH. Install Claude Code first.", err=True)
        raise SystemExit(1)

    if not identifier and not all_unnamed:
        click.echo("usage: seshi auto-name <id> or seshi auto-name --all", err=True)
        raise SystemExit(2)

    with open_db() as conn:
        if all_unnamed:
            sql = "SELECT * FROM sessions WHERE custom_name IS NULL AND is_archived = 0"
            params = []
            if ctx.obj.get("here_cwd"):
                sql += " AND cwd = ?"
                params.append(ctx.obj["here_cwd"])
            sql += " ORDER BY last_activity_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            for row in rows:
                _name_session(conn, row["session_id"])
        else:
            session = session_resolve(conn, identifier)
            if not session:
                click.echo(f"session not found: {identifier}", err=True)
                raise SystemExit(1)
            _name_session(conn, session.session_id)


def _name_session(conn, session_id):
    path = find_transcript_path(session_id)
    if not path:
        click.echo(f"  {session_id[:8]}: no transcript found", err=True)
        return

    messages = extract_messages(path, limit=5)
    if not messages:
        click.echo(f"  {session_id[:8]}: empty transcript", err=True)
        return

    summary = "\n".join(f"{m.role}: {m.text[:200]}" for m in messages)
    prompt = f"Summarize this Claude Code conversation in 3-5 words, kebab-case, lowercase, no quotes.\n\n{summary}"

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=30,
        )
        name = result.stdout.strip().strip('"').strip("'")
    except (subprocess.TimeoutExpired, OSError):
        click.echo(f"  {session_id[:8]}: claude command failed", err=True)
        return

    if not VALID_NAME_RE.match(name):
        click.echo(f"  {session_id[:8]}: invalid name returned: {name!r}", err=True)
        return

    conn.execute("UPDATE sessions SET custom_name = ? WHERE session_id = ?", (name, session_id))
    conn.commit()
    click.echo(f"  {session_id[:8]} → {name}")
