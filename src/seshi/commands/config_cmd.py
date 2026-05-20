import click

from seshi.cli import main
from seshi.db import open_db, get_setting, set_setting, DEFAULT_SETTINGS
from seshi.themes import THEMES

VALID_SORT_MODES = ("frecency", "recency", "frequency")


@main.command("config")
@click.argument("key", required=False)
@click.argument("value", required=False)
def config(key, value):
    """View or modify settings."""
    with open_db() as conn:
        if key is None:
            for k in sorted(DEFAULT_SETTINGS.keys()):
                v = get_setting(conn, k)
                click.echo(f"{k} = {v}")
            return

        if key not in DEFAULT_SETTINGS:
            available = ", ".join(sorted(DEFAULT_SETTINGS.keys()))
            click.echo(f"unknown setting '{key}'. Available: {available}", err=True)
            raise SystemExit(1)

        if value is None:
            v = get_setting(conn, key)
            click.echo(v)
            return

        if key == "sort_mode" and value not in VALID_SORT_MODES:
            click.echo(f"invalid value '{value}' for sort_mode. Expected: {', '.join(VALID_SORT_MODES)}", err=True)
            raise SystemExit(1)

        if key == "theme" and value not in THEMES:
            click.echo(f"invalid value '{value}' for theme. Expected: {', '.join(THEMES.keys())}", err=True)
            raise SystemExit(1)

        if key == "prune_days":
            try:
                n = int(value)
                if n < 0:
                    raise ValueError
            except ValueError:
                click.echo(f"invalid value '{value}' for prune_days. Expected: non-negative integer", err=True)
                raise SystemExit(1)

        set_setting(conn, key, value)
        click.echo(f"{key} = {value}")
