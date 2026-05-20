import os
import sys

import click

from seshi import __version__
from seshi.db import open_db
from seshi.drain import drain_queue
from seshi.paths import DB_PATH


class SeshiGroup(click.Group):
    def resolve_command(self, ctx, args):
        cmd_name = args[0] if args else None
        if cmd_name and cmd_name not in self.commands and not cmd_name.startswith("-"):
            return "resume", self.commands.get("resume"), args
        return super().resolve_command(ctx, args)


@click.group(cls=SeshiGroup, invoke_without_command=True)
@click.option("--no-color", is_flag=True, help="Disable color output")
@click.option("--here", is_flag=True, help="Filter to current directory")
@click.version_option(version=__version__, prog_name="seshi")
@click.pass_context
def main(ctx, no_color, here):
    """Seshi — global session manager and resumer."""
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["here_cwd"] = os.getcwd() if here else None

    if no_color:
        os.environ["NO_COLOR"] = "1"

    if DB_PATH.parent.exists():
        try:
            with open_db() as conn:
                drain_queue(conn)
        except Exception:
            pass

    if ctx.invoked_subcommand is None:
        from seshi.tui.app import launch_tui
        launch_tui(ctx.obj)


# Import commands to register them
from seshi.commands import doctor_cmd  # noqa: E402, F401
from seshi.commands import scan_cmd  # noqa: E402, F401
from seshi.commands import init_cmd  # noqa: E402, F401
from seshi.commands import last_cmd  # noqa: E402, F401
from seshi.commands import resume_cmd  # noqa: E402, F401
from seshi.commands import theme_cmd  # noqa: E402, F401
from seshi.commands import prune_cmd  # noqa: E402, F401
from seshi.commands import export_cmd  # noqa: E402, F401
from seshi.commands import grep_cmd  # noqa: E402, F401
from seshi.commands import auto_name_cmd  # noqa: E402, F401
from seshi.commands import list_cmd  # noqa: E402, F401
from seshi.commands import rename_cmd  # noqa: E402, F401
from seshi.commands import tag_cmd  # noqa: E402, F401
from seshi.commands import favorite_cmd  # noqa: E402, F401
from seshi.commands import delete_cmd  # noqa: E402, F401
from seshi.commands import archive_cmd  # noqa: E402, F401
from seshi.commands import stats_cmd  # noqa: E402, F401
from seshi.commands import config_cmd  # noqa: E402, F401
from seshi.commands import project_cmd  # noqa: E402, F401
from seshi.commands import uninstall_cmd  # noqa: E402, F401
