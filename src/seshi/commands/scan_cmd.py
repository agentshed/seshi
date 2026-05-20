import click

from seshi.cli import main
from seshi.db import open_db
from seshi.scan import scan_projects


@main.command("scan")
@click.option("--verbose", is_flag=True, help="Show progress")
def scan(verbose):
    """Backfill sessions from Claude Code transcript files on disk."""
    with open_db() as conn:
        count = scan_projects(conn, verbose=verbose)
    click.echo(f"discovered {count} new session{'s' if count != 1 else ''}.")
