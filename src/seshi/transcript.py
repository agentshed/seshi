import json
import os
from dataclasses import dataclass
from pathlib import Path

from seshi.paths import CLAUDE_PROJECTS


@dataclass
class TranscriptSummary:
    first_prompt: str | None
    message_count: int
    token_count: int
    first_ts: int | None
    last_ts: int | None


@dataclass
class Message:
    role: str
    text: str
    timestamp: str | None = None


def parse_transcript(path: Path) -> TranscriptSummary:
    first_prompt = None
    message_count = 0
    token_count = 0
    first_ts = None
    last_ts = None

    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                message_count += 1

                ts_str = obj.get("timestamp")
                if ts_str:
                    from datetime import datetime, timezone
                    try:
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        ts_int = int(dt.timestamp())
                        if first_ts is None:
                            first_ts = ts_int
                        last_ts = ts_int
                    except (ValueError, OSError):
                        pass

                msg = obj.get("message", {})
                usage = msg.get("usage", {})
                token_count += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

                if first_prompt is None and msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                content = block.get("text", "")
                                break
                        else:
                            content = ""
                    if isinstance(content, str) and content.strip():
                        first_prompt = content.strip()[:200]
    except OSError:
        pass

    return TranscriptSummary(
        first_prompt=first_prompt,
        message_count=message_count,
        token_count=token_count,
        first_ts=first_ts,
        last_ts=last_ts,
    )


def extract_messages(path: Path, limit: int | None = None) -> list[Message]:
    messages = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = obj.get("message", {})
                role = msg.get("role")
                if not role:
                    continue

                content = msg.get("content", "")
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                parts.append(block.get("text", ""))
                            elif block.get("type") == "tool_use":
                                parts.append(f"[tool: {block.get('name', 'unknown')}]")
                    content = "\n".join(parts)

                if isinstance(content, str):
                    text = " ".join(content.split())[:200]
                    messages.append(Message(
                        role=role,
                        text=text,
                        timestamp=obj.get("timestamp"),
                    ))

                if limit and len(messages) >= limit:
                    break
    except OSError:
        pass
    return messages


def find_transcript_path(session_id: str) -> Path | None:
    if not CLAUDE_PROJECTS.is_dir():
        return None

    for project_dir in CLAUDE_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue
        jsonl = project_dir / f"{session_id}.jsonl"
        if jsonl.is_file():
            return jsonl
        session_dir = project_dir / session_id
        if session_dir.is_dir():
            for f in session_dir.iterdir():
                if f.suffix == ".jsonl":
                    return f
    return None


def get_existing_session_ids() -> set[str]:
    from seshi.paths import UUID_RE
    ids: set[str] = set()
    if not CLAUDE_PROJECTS.is_dir():
        return ids
    for project_dir in CLAUDE_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue
        for entry in project_dir.iterdir():
            if entry.name == "skill-injections.jsonl":
                continue
            if entry.is_file() and entry.suffix == ".jsonl" and UUID_RE.match(entry.stem):
                ids.add(entry.stem)
            elif entry.is_dir() and UUID_RE.match(entry.name):
                if any(f.suffix == ".jsonl" for f in entry.iterdir()):
                    ids.add(entry.name)
    return ids
