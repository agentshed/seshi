import shutil

import click

from seshi.cli import main
from seshi.hook_manager import uninstall_hook
from seshi.paths import SESHI_DIR


@main.command("uninstall")
@click.option("--purge", is_flag=True, help="Also delete ~/.seshi/ directory")
@click.option("--force", is_flag=True, help="Skip confirmation for --purge")
def uninstall(purge, force):
    """Remove hook and settings patch."""
    uninstall_hook()
    click.echo("hook removed and settings unpatched.")

    if purge:
        if not force:
            try:
                tty = open("/dev/tty", "r")
                tty_out = open("/dev/tty", "w")
                tty_out.write(f"delete {SESHI_DIR}? This removes all session data. [y/N] ")
                tty_out.flush()
                answer = tty.readline().strip().lower()
                tty.close()
                tty_out.close()
                if answer not in ("y", "yes"):
                    return
            except OSError:
                click.echo("use --force with --purge to skip confirmation.", err=True)
                raise SystemExit(1)

        if SESHI_DIR.exists():
            shutil.rmtree(SESHI_DIR)
            click.echo(f"deleted {SESHI_DIR}")
