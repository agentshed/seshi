import click

from seshi.cli import main
from seshi.db import open_db, get_setting
from seshi.shell_init import generate_init, detect_shell


@main.command("init")
@click.argument("shell", required=False)
@click.option("--completions", is_flag=True, help="Print only completion tokens")
def init(shell, completions):
    """Print shell wrapper for eval. Auto-detects shell if omitted."""
    if completions:
        _print_completions()
        return

    shell = shell or detect_shell()
    click.echo(generate_init(shell, completions_only=False), nl=False)


def _print_completions():
    subcommands = [
        "resume", "list", "rename", "tag", "favorite", "delete", "archive",
        "stats", "config", "scan", "doctor", "prune", "export", "grep",
        "auto-name", "theme", "init", "uninstall", "last", "here",
        "project",
    ]
    names = []
    try:
        with open_db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT custom_name FROM sessions WHERE custom_name IS NOT NULL"
            ).fetchall()
            names = [r["custom_name"] for r in rows]
    except Exception:
        pass
    click.echo(" ".join(subcommands + names))
