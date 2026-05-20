from pathlib import Path
import itertools
import os
import re

SESHI_DIR = Path.home() / ".seshi"
DB_PATH = SESHI_DIR / "db.sqlite"
QUEUE_PATH = SESHI_DIR / "queue.jsonl"
HOOK_PATH = SESHI_DIR / "hook.sh"
CLAUDE_DIR = Path.home() / ".claude"
CLAUDE_PROJECTS = CLAUDE_DIR / "projects"
CLAUDE_SETTINGS = CLAUDE_DIR / "settings.json"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def unsanitize_path(name: str) -> list[str]:
    if not name:
        return ["/"]

    result = "/"
    rest = name[1:] if name.startswith("-") else name
    if not rest:
        return [result]

    dash_positions = [i for i, c in enumerate(rest) if c == "-"]
    if not dash_positions:
        return [result + rest]

    if len(dash_positions) > 6:
        all_slashes = result + rest.replace("-", "/")
        candidates = [all_slashes]
        for pos in dash_positions:
            candidate = result + rest[:pos] + "/" + rest[pos + 1:]
            if candidate not in candidates:
                candidates.append(candidate)
        return candidates

    candidates = []
    for combo in itertools.product(["/", "-"], repeat=len(dash_positions)):
        chars = list(rest)
        for pos, replacement in zip(dash_positions, combo):
            chars[pos] = replacement
        path = result + "".join(chars)
        path = path.replace("/.", "/.")
        if path.startswith("//"):
            path = "/." + path[2:]
        candidates.append(path)

    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def resolve_best_cwd(name: str) -> str:
    candidates = unsanitize_path(name)
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0] if candidates else "/"
