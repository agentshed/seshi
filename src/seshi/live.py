import json
import os
import re
import subprocess
from dataclasses import dataclass, field

from seshi.paths import CLAUDE_JOBS, CLAUDE_DIR
from seshi.transcript import find_transcript_path


@dataclass
class ToolCall:
    name: str
    summary: str


@dataclass
class LiveInfo:
    session_id: str
    pid: int
    kind: str
    status: str
    detail: str | None
    name: str | None
    daemon_short: str | None
    cwd: str
    transcript_path: str | None = None
    tools: list[ToolCall] = field(default_factory=list)


_HEX8_RE = re.compile(r"^[0-9a-f]{8}$")


def _read_state_json(daemon_short: str) -> dict:
    if not _HEX8_RE.match(daemon_short):
        return {}
    state_path = CLAUDE_JOBS / daemon_short / "state.json"
    try:
        return json.loads(state_path.read_text())
    except Exception:
        return {}


def _summarize_tool_input(name: str, inp: dict) -> str:
    if name == "Bash":
        return inp.get("command", "")[:120]
    if name in ("Read", "Write"):
        return inp.get("file_path", "")
    if name == "Edit":
        fp = inp.get("file_path", "")
        old = inp.get("old_string", "")[:40]
        return f"{fp}" + (f"  {old}…" if old else "")
    if name == "Agent":
        return inp.get("description", inp.get("prompt", ""))[:80]
    if name in ("WebFetch", "WebSearch"):
        return inp.get("url", inp.get("query", ""))[:80]
    return json.dumps(inp)[:80]


def _extract_live_tools(transcript_path: str) -> list[ToolCall]:
    try:
        size = os.path.getsize(transcript_path)
        read_bytes = min(size, 64 * 1024)
        with open(transcript_path, "rb") as f:
            f.seek(max(0, size - read_bytes))
            tail = f.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    lines = tail.strip().split("\n")

    tools: list[ToolCall] = []
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        msg = obj.get("message", {})
        if msg.get("role") != "assistant":
            if msg.get("role") == "user" and tools:
                break
            continue
        for block in msg.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "unknown")
                summary = _summarize_tool_input(name, block.get("input", {}))
                tools.append(ToolCall(name=name, summary=summary))
        if tools:
            break

    return tools


def fetch_live_sessions() -> dict[str, LiveInfo]:
    try:
        result = subprocess.run(
            ["claude", "agents", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {}
        entries = json.loads(result.stdout)
        if not isinstance(entries, list):
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError,
            OSError, ValueError):
        return {}

    live: dict[str, LiveInfo] = {}
    for entry in entries:
        sid = entry.get("sessionId")
        if not sid:
            continue
        daemon_short = sid[:8]
        detail = None
        transcript_path = None
        tools: list[ToolCall] = []

        if entry.get("kind") == "background":
            state = _read_state_json(daemon_short)
            detail = state.get("detail")
            transcript_path = state.get("linkScanPath")

        if not transcript_path:
            found = find_transcript_path(sid)
            if found:
                transcript_path = str(found)

        if transcript_path:
            tp = os.path.realpath(transcript_path)
            claude_root = str(CLAUDE_DIR)
            if not tp.startswith(claude_root + os.sep):
                transcript_path = None

        if transcript_path and entry.get("status") == "busy":
            tools = _extract_live_tools(transcript_path)

        live[sid] = LiveInfo(
            session_id=sid,
            pid=entry.get("pid", 0),
            kind=entry.get("kind", "interactive"),
            status=entry.get("status", "idle"),
            detail=detail,
            name=entry.get("name"),
            daemon_short=daemon_short,
            cwd=entry.get("cwd", ""),
            transcript_path=transcript_path,
            tools=tools,
        )

    return live
