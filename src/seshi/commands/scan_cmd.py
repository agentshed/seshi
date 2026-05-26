import click

from seshi.cli import main
from seshi.db import open_db
from seshi.scan import fix_prompts as _fix_prompts, scan_projects


@main.command("scan")
@click.option("--verbose", is_flag=True, help="Show progress")
@click.option("--fix-prompts", is_flag=True, help="Re-derive first_prompt from transcripts")
def scan(verbose, fix_prompts):
    """Backfill sessions from Claude Code transcript files on disk."""
    with open_db() as conn:
        count = scan_projects(conn, verbose=verbose)
        click.echo(f"discovered {count} new session{'s' if count != 1 else ''}.")
        if fix_prompts:
            fixed = _fix_prompts(conn, verbose=verbose)
            click.echo(f"updated {fixed} session prompt{'s' if fixed != 1 else ''}.")
