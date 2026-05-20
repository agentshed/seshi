import os

import click

from seshi.cli import main
from seshi.db import open_db


@main.group("project")
def project_group():
    """Manage project favorites and names."""
    pass


@project_group.command("favorite")
@click.argument("cwd", required=False)
def project_favorite(cwd):
    """Toggle project favorite status."""
    cwd = cwd or os.getcwd()
    with open_db() as conn:
        existing = conn.execute("SELECT 1 FROM project_favorites WHERE cwd = ?", (cwd,)).fetchone()
        if existing:
            conn.execute("DELETE FROM project_favorites WHERE cwd = ?", (cwd,))
            conn.commit()
            click.echo(f"unfavorited {cwd}")
        else:
            conn.execute("INSERT INTO project_favorites (cwd) VALUES (?)", (cwd,))
            conn.commit()
            click.echo(f"favorited {cwd}")


@project_group.command("rename")
@click.argument("name")
@click.argument("cwd", required=False)
def project_rename(name, cwd):
    """Set a display name for a project."""
    cwd = cwd or os.getcwd()
    with open_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO project_favorites (cwd, custom_name) VALUES (?, ?)",
            (cwd, name),
        )
        conn.commit()
        click.echo(f"project {cwd} → {name}")
