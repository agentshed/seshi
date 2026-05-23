import json

import click

from seshi.cli import main
from seshi.db import open_db
from seshi.search import list_sessions
from seshi.time_utils import relative_time
from seshi.lang_detect import detect_language


@main.command("list")
@click.option("--json", "fmt", flag_value="json", help="JSON output")
@click.option("--tsv", "fmt", flag_value="tsv", help="TSV output")
@click.option("--limit", type=int, help="Max sessions")
@click.option("--tag", multiple=True, help="Filter by tag (repeatable)")
@click.option("--sort", type=click.Choice(["frecency", "recency", "frequency"]), help="Sort mode")
@click.option("--archived", is_flag=True, help="Include archived sessions")
@click.option("--here", is_flag=True, help="Filter to current directory")
@click.pass_context
def list_cmd(ctx, fmt, limit, tag, sort, archived, here):
    """List sessions non-interactively."""
    from seshi.cli import _merge_here
    _merge_here(ctx, here)
    with open_db() as conn:
        sort_mode = sort or "frecency"
        sessions = list_sessions(
            conn,
            filter_cwd=ctx.obj.get("here_cwd"),
            tags=list(tag) if tag else None,
            include_archived=archived,
            sort_mode=sort_mode,
            limit=limit,
        )

    if fmt == "json":
        data = []
        for s in sessions:
            data.append({
                "session_id": s.session_id,
                "cwd": s.cwd,
                "custom_name": s.custom_name,
                "first_prompt": s.first_prompt,
                "is_favorite": s.is_favorite,
                "is_archived": s.is_archived,
                "message_count": s.message_count,
                "token_count": s.token_count,
                "status": s.status,
                "created_at": s.created_at,
                "last_activity_at": s.last_activity_at,
                "git_branch": s.git_branch,
            })
        click.echo(json.dumps(data, indent=2))
        return

    if fmt == "tsv":
        click.echo("session_id\tcwd\tcustom_name\tfirst_prompt\tmessage_count\ttoken_count\tlast_activity_at")
        for s in sessions:
            prompt = (s.first_prompt or "")[:60].replace("\t", " ")
            click.echo(f"{s.session_id}\t{s.cwd}\t{s.custom_name or ''}\t{prompt}\t{s.message_count}\t{s.token_count}\t{s.last_activity_at}")
        return

    if not sessions:
        click.echo("no sessions found.")
        return

    for s in sessions:
        fav = "*" if s.is_favorite else " "
        lang = detect_language(s.cwd)
        lang_str = f" {lang:>3}" if lang else "    "
        title = s.custom_name or (s.first_prompt or "(untitled)")[:38]
        rel = relative_time(s.last_activity_at)
        click.echo(f" {fav}{lang_str}  {title:<38}  {s.cwd:<30}  {rel}")
