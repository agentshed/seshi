"""Tests for live session detection (src/seshi/live.py)."""
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from seshi.live import LiveInfo, ToolCall, fetch_live_sessions, _extract_live_tools, _summarize_tool_input


def _agents_json(*entries):
    """Helper: mock subprocess.run returning claude agents --json output."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = json.dumps(entries)
    return result


# ── Positive cases ──────────────────────────────────────────────────

def test_fetch_parses_background_session(tmp_path):
    entry = {
        "pid": 123,
        "cwd": "/home/user/project",
        "kind": "background",
        "startedAt": 1000,
        "sessionId": "3a70a47d-89ee-4a89-abcc-9326094109a5",
        "status": "busy",
        "name": "fix tests",
    }
    state = {"detail": "Running pytest...", "state": "working"}
    jobs = tmp_path / "jobs" / "3a70a47d"
    jobs.mkdir(parents=True)
    (jobs / "state.json").write_text(json.dumps(state))

    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)), \
         patch("seshi.live.CLAUDE_JOBS", tmp_path / "jobs"):
        result = fetch_live_sessions()

    assert "3a70a47d-89ee-4a89-abcc-9326094109a5" in result
    info = result["3a70a47d-89ee-4a89-abcc-9326094109a5"]
    assert info.kind == "background"
    assert info.status == "busy"
    assert info.detail == "Running pytest..."
    assert info.daemon_short == "3a70a47d"
    assert info.name == "fix tests"
    assert info.pid == 123


def test_fetch_parses_interactive_session():
    entry = {
        "pid": 456,
        "cwd": "/home/user/seshi",
        "kind": "interactive",
        "startedAt": 2000,
        "sessionId": "abcd1234-0000-0000-0000-000000000000",
        "status": "idle",
    }
    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)):
        result = fetch_live_sessions()

    info = result["abcd1234-0000-0000-0000-000000000000"]
    assert info.kind == "interactive"
    assert info.detail is None


def test_fetch_multiple_sessions():
    entries = [
        {"pid": 1, "cwd": "/a", "kind": "background", "startedAt": 100, "sessionId": "aaaa0000-0000-0000-0000-000000000000", "status": "busy"},
        {"pid": 2, "cwd": "/b", "kind": "background", "startedAt": 200, "sessionId": "bbbb0000-0000-0000-0000-000000000000", "status": "idle"},
        {"pid": 3, "cwd": "/c", "kind": "interactive", "startedAt": 300, "sessionId": "cccc0000-0000-0000-0000-000000000000", "status": "needs_input"},
    ]
    with patch("seshi.live.subprocess.run", return_value=_agents_json(*entries)):
        result = fetch_live_sessions()
    assert len(result) == 3


def test_fetch_enriches_from_state_json(tmp_path):
    entry = {
        "pid": 10, "cwd": "/x", "kind": "background", "startedAt": 100,
        "sessionId": "deadbeef-0000-0000-0000-000000000000", "status": "busy",
    }
    jobs = tmp_path / "jobs" / "deadbeef"
    jobs.mkdir(parents=True)
    (jobs / "state.json").write_text(json.dumps({"detail": "Edit src/foo.py", "state": "working"}))

    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)), \
         patch("seshi.live.CLAUDE_JOBS", tmp_path / "jobs"):
        result = fetch_live_sessions()

    assert result["deadbeef-0000-0000-0000-000000000000"].detail == "Edit src/foo.py"


def test_fetch_status_busy():
    entry = {"pid": 1, "cwd": "/", "kind": "interactive", "startedAt": 0, "sessionId": "a0000000-0000-0000-0000-000000000000", "status": "busy"}
    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)):
        result = fetch_live_sessions()
    assert result["a0000000-0000-0000-0000-000000000000"].status == "busy"


def test_fetch_status_needs_input():
    entry = {"pid": 1, "cwd": "/", "kind": "interactive", "startedAt": 0, "sessionId": "b0000000-0000-0000-0000-000000000000", "status": "needs_input"}
    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)):
        result = fetch_live_sessions()
    assert result["b0000000-0000-0000-0000-000000000000"].status == "needs_input"


def test_fetch_status_idle():
    entry = {"pid": 1, "cwd": "/", "kind": "interactive", "startedAt": 0, "sessionId": "c0000000-0000-0000-0000-000000000000", "status": "idle"}
    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)):
        result = fetch_live_sessions()
    assert result["c0000000-0000-0000-0000-000000000000"].status == "idle"


def test_daemon_short_derivation():
    entry = {"pid": 1, "cwd": "/", "kind": "interactive", "startedAt": 0, "sessionId": "3a70a47d-89ee-4a89-abcc-9326094109a5", "status": "idle"}
    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)):
        result = fetch_live_sessions()
    assert result["3a70a47d-89ee-4a89-abcc-9326094109a5"].daemon_short == "3a70a47d"


# ── Negative cases ──────────────────────────────────────────────────

def test_fetch_returns_empty_when_claude_not_found():
    with patch("seshi.live.subprocess.run", side_effect=FileNotFoundError):
        assert fetch_live_sessions() == {}


def test_fetch_returns_empty_on_timeout():
    with patch("seshi.live.subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 5)):
        assert fetch_live_sessions() == {}


def test_fetch_returns_empty_on_nonzero_exit():
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    with patch("seshi.live.subprocess.run", return_value=result):
        assert fetch_live_sessions() == {}


def test_fetch_returns_empty_on_malformed_json():
    result = MagicMock()
    result.returncode = 0
    result.stdout = "not json at all"
    with patch("seshi.live.subprocess.run", return_value=result):
        assert fetch_live_sessions() == {}


def test_fetch_returns_empty_on_empty_output():
    result = MagicMock()
    result.returncode = 0
    result.stdout = ""
    with patch("seshi.live.subprocess.run", return_value=result):
        assert fetch_live_sessions() == {}


def test_fetch_returns_empty_on_null_output():
    result = MagicMock()
    result.returncode = 0
    result.stdout = "null"
    with patch("seshi.live.subprocess.run", return_value=result):
        assert fetch_live_sessions() == {}


# ── Edge cases ──────────────────────────────────────────────────────

def test_fetch_skips_entry_without_session_id():
    entries = [
        {"pid": 1, "cwd": "/a", "kind": "interactive", "startedAt": 100},
        {"pid": 2, "cwd": "/b", "kind": "interactive", "startedAt": 200, "sessionId": "ok000000-0000-0000-0000-000000000000", "status": "idle"},
    ]
    with patch("seshi.live.subprocess.run", return_value=_agents_json(*entries)):
        result = fetch_live_sessions()
    assert len(result) == 1
    assert "ok000000-0000-0000-0000-000000000000" in result


def test_fetch_handles_missing_state_json(tmp_path):
    entry = {"pid": 1, "cwd": "/", "kind": "background", "startedAt": 0, "sessionId": "aa000000-0000-0000-0000-000000000000", "status": "busy"}
    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)), \
         patch("seshi.live.CLAUDE_JOBS", tmp_path / "jobs"):
        result = fetch_live_sessions()
    assert result["aa000000-0000-0000-0000-000000000000"].detail is None


def test_fetch_handles_corrupt_state_json(tmp_path):
    entry = {"pid": 1, "cwd": "/", "kind": "background", "startedAt": 0, "sessionId": "bb000000-0000-0000-0000-000000000000", "status": "busy"}
    jobs = tmp_path / "jobs" / "bb000000"
    jobs.mkdir(parents=True)
    (jobs / "state.json").write_bytes(b"\x00\xff garbled")
    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)), \
         patch("seshi.live.CLAUDE_JOBS", tmp_path / "jobs"):
        result = fetch_live_sessions()
    assert result["bb000000-0000-0000-0000-000000000000"].detail is None


def test_fetch_handles_state_json_missing_detail(tmp_path):
    entry = {"pid": 1, "cwd": "/", "kind": "background", "startedAt": 0, "sessionId": "cc000000-0000-0000-0000-000000000000", "status": "idle"}
    jobs = tmp_path / "jobs" / "cc000000"
    jobs.mkdir(parents=True)
    (jobs / "state.json").write_text(json.dumps({"state": "idle"}))
    with patch("seshi.live.subprocess.run", return_value=_agents_json(entry)), \
         patch("seshi.live.CLAUDE_JOBS", tmp_path / "jobs"):
        result = fetch_live_sessions()
    assert result["cc000000-0000-0000-0000-000000000000"].detail is None


def test_fetch_empty_array():
    with patch("seshi.live.subprocess.run", return_value=_agents_json()):
        assert fetch_live_sessions() == {}


# ── _summarize_tool_input tests ─────────────────────────────────────

def test_summarize_bash():
    assert _summarize_tool_input("Bash", {"command": "uv run pytest -x"}) == "uv run pytest -x"


def test_summarize_read():
    assert _summarize_tool_input("Read", {"file_path": "/src/main.py"}) == "/src/main.py"


def test_summarize_write():
    assert _summarize_tool_input("Write", {"file_path": "/out.txt"}) == "/out.txt"


def test_summarize_edit():
    result = _summarize_tool_input("Edit", {"file_path": "foo.py", "old_string": "hello world"})
    assert "foo.py" in result


def test_summarize_agent():
    assert "search" in _summarize_tool_input("Agent", {"description": "search codebase"})


def test_summarize_unknown():
    result = _summarize_tool_input("CustomTool", {"a": 1})
    assert isinstance(result, str)


def test_summarize_bash_truncates():
    long_cmd = "x" * 200
    result = _summarize_tool_input("Bash", {"command": long_cmd})
    assert len(result) <= 120


# ── _extract_live_tools tests ───────────────────────────────────────

def test_extract_live_tools_from_transcript(tmp_path):
    transcript = tmp_path / "session.jsonl"
    lines = [
        json.dumps({"message": {"role": "user", "content": [{"type": "text", "text": "fix the bug"}]}}),
        json.dumps({"message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -x"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "src/main.py"}},
        ]}}),
    ]
    transcript.write_text("\n".join(lines))
    tools = _extract_live_tools(str(transcript))
    assert len(tools) == 2
    assert tools[0].name == "Bash"
    assert "pytest" in tools[0].summary
    assert tools[1].name == "Read"


def test_extract_live_tools_empty_file(tmp_path):
    transcript = tmp_path / "empty.jsonl"
    transcript.write_text("")
    tools = _extract_live_tools(str(transcript))
    assert tools == []


def test_extract_live_tools_missing_file():
    tools = _extract_live_tools("/nonexistent/path.jsonl")
    assert tools == []


def test_extract_live_tools_stops_at_user_message(tmp_path):
    transcript = tmp_path / "session.jsonl"
    lines = [
        json.dumps({"message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "echo old"}},
        ]}}),
        json.dumps({"message": {"role": "user", "content": [{"type": "text", "text": "now do this"}]}}),
        json.dumps({"message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "new.py"}},
        ]}}),
    ]
    transcript.write_text("\n".join(lines))
    tools = _extract_live_tools(str(transcript))
    assert len(tools) == 1
    assert tools[0].name == "Read"
