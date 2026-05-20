import os
import shutil

import click

from seshi.cli import main
from seshi.db import open_db, init_schema
from seshi.hook_manager import install_hook
from seshi.paths import SESHI_DIR, HOOK_PATH, DB_PATH, CLAUDE_SETTINGS
from seshi.settings import patch_settings


@main.command("doctor")
@click.option("--fix", is_flag=True, help="Auto-fix problems")
def doctor(fix):
    """Health check for Seshi installation."""
    checks = [
        ("Registry directory", SESHI_DIR.is_dir(), _fix_dir if fix else None),
        ("Hook installed", HOOK_PATH.exists() and os.access(str(HOOK_PATH), os.X_OK), _fix_hook if fix else None),
        ("Registry DB", DB_PATH.exists(), _fix_db if fix else None),
        ("Settings patched", _check_settings_patched(), _fix_settings if fix else None),
        ("Claude on PATH", shutil.which("claude") is not None, None),
    ]

    all_ok = True
    for name, ok, fixer in checks:
        if ok:
            click.echo(f"  [OK]   {name}")
        else:
            all_ok = False
            if fix and fixer:
                try:
                    fixer()
                    click.echo(f"  [FIXED] {name}")
                except Exception as e:
                    click.echo(f"  [FAIL] {name} — {e}", err=True)
            else:
                click.echo(f"  [FAIL] {name}")

    if not all_ok and not fix:
        click.echo("\nRun `seshi doctor --fix` to auto-repair.")
        raise SystemExit(1)


def _check_settings_patched() -> bool:
    if not CLAUDE_SETTINGS.exists():
        return False
    import json
    try:
        data = json.loads(CLAUDE_SETTINGS.read_text())
        hooks = data.get("hooks", {})
        hook_str = str(HOOK_PATH)
        for event in ("SessionStart", "Stop"):
            entries = hooks.get(event, [])
            found = any(
                hook_str in hh.get("command", "")
                for h in entries
                for hh in h.get("hooks", [])
            )
            if not found:
                return False
        return True
    except (json.JSONDecodeError, KeyError):
        return False


def _fix_dir():
    SESHI_DIR.mkdir(parents=True, exist_ok=True)


def _fix_hook():
    install_hook()


def _fix_db():
    with open_db() as conn:
        init_schema(conn)


def _fix_settings():
    patch_settings()
