import json
import os
import sys

import click

from seshi.cli import main
from seshi.db import open_db
from seshi.paths import CLAUDE_PROJECTS
from seshi.time_utils import relative_time


@main.command("grep")
@click.argument("pattern")
@click.option("--limit", type=int, default=3, help="Max matches per session")
@click.option("--role", type=click.Choice(["user", "assistant"]), help="Filter by role")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.option("--here", is_flag=True, help="Filter to current directory")
@click.pass_context
def grep_cmd(ctx, pattern, limit, role, as_json, here):
    """Search message content across all session transcripts."""
    from seshi.cli import _merge_here
    _merge_here(ctx, here)
    if not CLAUDE_PROJECTS.is_dir():
        click.echo(f"projects directory not found: {CLAUDE_PROJECTS}", err=True)
        raise SystemExit(1)

    use_color = sys.stdout.isatty() and not ctx.obj.get("no_color")
    filter_cwd = ctx.obj.get("here_cwd")
    pattern_lower = pattern.lower()
    results = []

    with open_db() as conn:
        sessions = conn.execute(
            "SELECT session_id, cwd, last_activity_at FROM sessions WHERE is_archived = 0 ORDER BY last_activity_at DESC"
        ).fetchall()

        session_map = {r["session_id"]: r for r in sessions}

    for project_dir in CLAUDE_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue
        for entry in project_dir.iterdir():
            if entry.name in ("skill-injections.jsonl",):
                continue
            if entry.is_dir() and entry.name in ("subagents", "tool-results"):
                continue
            if not entry.is_file() or entry.suffix != ".jsonl":
                continue

            session_id = entry.stem
            session_info = session_map.get(session_id)
            if not session_info:
                continue
            if filter_cwd and session_info["cwd"] != filter_cwd:
                continue

            matches = []
            try:
                with open(entry) as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg = obj.get("message", {})
                        msg_role = msg.get("role")
                        if role and msg_role != role:
                            continue
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            content = " ".join(
                                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                            )
                        if not isinstance(content, str):
                            continue
                        if pattern_lower in content.lower():
                            snippet = content.strip()[:120]
                            matches.append({"role": msg_role, "snippet": snippet})
                            if len(matches) >= limit:
                                break
            except OSError:
                continue

            if matches:
                cwd = session_info["cwd"]
                home = os.path.expanduser("~")
                if cwd.startswith(home):
                    cwd = "~" + cwd[len(home):]
                results.append({
                    "session_id": session_id,
                    "cwd": cwd,
                    "last_activity_at": session_info["last_activity_at"],
                    "matches": matches,
                })

    results.sort(key=lambda r: r["last_activity_at"], reverse=True)

    if as_json:
        flat = []
        for r in results:
            for m in r["matches"]:
                flat.append({
                    "session_id": r["session_id"],
                    "cwd": r["cwd"],
                    "last_activity_at": r["last_activity_at"],
                    "role": m["role"],
                    "snippet": m["snippet"],
                })
        click.echo(json.dumps(flat, indent=2))
        return

    if not results:
        click.echo("no matches found.")
        return

    for r in results:
        sid = r["session_id"][:8]
        rel = relative_time(r["last_activity_at"])
        click.echo(f"{sid}  {r['cwd']}  {rel}")
        for m in r["matches"]:
            snippet = m["snippet"]
            if use_color:
                idx = snippet.lower().find(pattern_lower)
                if idx >= 0:
                    before = snippet[:idx]
                    match = snippet[idx:idx + len(pattern)]
                    after = snippet[idx + len(pattern):]
                    snippet = f"{before}\033[38;2;224;138;94m{match}\033[0m{after}"
            click.echo(f"  {m['role']:>5}  {snippet}")
