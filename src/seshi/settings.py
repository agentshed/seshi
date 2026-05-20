import json
from pathlib import Path

from seshi.paths import CLAUDE_SETTINGS, HOOK_PATH


def patch_settings() -> None:
    hook_cmd = str(HOOK_PATH)

    if CLAUDE_SETTINGS.exists():
        data = json.loads(CLAUDE_SETTINGS.read_text())
    else:
        CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    hooks = data.setdefault("hooks", {})

    for event in ("SessionStart", "Stop"):
        command = f"{hook_cmd} {'start' if event == 'SessionStart' else 'stop'}"
        entries = hooks.setdefault(event, [])
        already = any(
            h.get("hooks", [{}])[0].get("command", "") == command
            for h in entries
            if h.get("hooks")
        )
        if not already:
            entries.append({
                "matcher": ".*",
                "hooks": [{"type": "command", "command": command}],
            })

    CLAUDE_SETTINGS.write_text(json.dumps(data, indent=2) + "\n")


def unpatch_settings() -> None:
    if not CLAUDE_SETTINGS.exists():
        return

    data = json.loads(CLAUDE_SETTINGS.read_text())
    hooks = data.get("hooks", {})
    hook_prefix = str(HOOK_PATH)

    for event in ("SessionStart", "Stop"):
        entries = hooks.get(event, [])
        hooks[event] = [
            h for h in entries
            if not any(
                hook_prefix in hh.get("command", "")
                for hh in h.get("hooks", [])
            )
        ]
        if not hooks[event]:
            del hooks[event]

    if not hooks:
        data.pop("hooks", None)

    CLAUDE_SETTINGS.write_text(json.dumps(data, indent=2) + "\n")
