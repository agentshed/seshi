import click

from seshi.cli import main
from seshi.db import open_db, get_setting, set_setting
from seshi.themes import THEMES, DEFAULT_THEME, get_theme


@main.command("theme")
@click.argument("action", required=False)
def theme(action):
    """Manage TUI theme. Usage: theme list | theme <name> | theme reset"""
    if not action or action == "list":
        with open_db() as conn:
            current = get_setting(conn, "theme") or DEFAULT_THEME
        for name in THEMES:
            marker = " *" if name == current else ""
            palette = THEMES[name]
            click.echo(f"  {name}{marker}  ({palette.accent})")
        return

    if action == "reset":
        with open_db() as conn:
            set_setting(conn, "theme", DEFAULT_THEME)
        click.echo(f"theme reset to {DEFAULT_THEME}")
        return

    if action not in THEMES:
        click.echo(f"unknown theme '{action}'. Available: {', '.join(THEMES.keys())}", err=True)
        raise SystemExit(1)

    with open_db() as conn:
        set_setting(conn, "theme", action)
    click.echo(f"theme set to {action}")
