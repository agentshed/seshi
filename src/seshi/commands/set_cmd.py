"""``seshi set`` / ``seshi unset`` — persistent Claude Code CLI flag defaults."""

import click

from seshi.cli import main
from seshi.db import open_db
from seshi.claude_flags import (
    build_args,
    get_flags,
    reset_flags,
    set_flag,
    unset_flag,
)


@main.command("set")
@click.argument("flag", required=False)
@click.argument("value", required=False)
@click.option("--reset", "do_reset", is_flag=True, help="Reset flag(s) to defaults")
@click.option("--preview", is_flag=True, help="Print the assembled CLI args")
def set_cmd(flag, value, do_reset, preview):
    """View or set persistent Claude Code CLI flags."""
    with open_db() as conn:
        if preview:
            args = build_args(conn)
            click.echo(" ".join(args) if args else "(no flags set)")
            return

        if do_reset:
            reset_flags(conn, flag)
            click.echo("reset to defaults" if flag is None else f"reset {flag}")
            return

        if flag is None:
            flags = get_flags(conn)
            if not flags:
                click.echo("(no flags set)")
                return
            for k in sorted(flags):
                click.echo(f"{k} = {flags[k]}")
            return

        if value is None:
            value = "true"

        set_flag(conn, flag, value)
        click.echo(f"{flag} = {value}")


@main.command("unset")
@click.argument("flag", required=True)
def unset_cmd(flag):
    """Remove a persistent Claude Code CLI flag."""
    with open_db() as conn:
        unset_flag(conn, flag)
        click.echo(f"unset {flag}")
