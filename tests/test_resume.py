import json
from seshi.resume import build_resume_line, shell_quote
from seshi.models import Session


def _session(cwd="/home/user", argv=None, session_id="test-id"):
    argv_json = json.dumps(argv or ["claude"])
    return Session(
        session_id=session_id, cwd=cwd, launch_argv_json=argv_json,
        env_json=None, git_branch=None, git_sha=None, first_prompt=None,
        custom_name=None, is_favorite=0, is_archived=0, is_backfilled=0,
        message_count=0, token_count=0, status=None,
        created_at=1000, last_activity_at=1000, origin_host=None, schema_version=1,
    )


def test_basic_resume_line():
    s = _session()
    line = build_resume_line(s)
    assert line.startswith("cd ")
    assert "&& exec claude" in line
    assert "--resume test-id" in line
    assert line.endswith("\n")


def test_shell_quote_safe():
    assert shell_quote("claude") == "claude"
    assert shell_quote("/usr/bin/claude") == "/usr/bin/claude"


def test_shell_quote_special():
    assert shell_quote("hello world") == "'hello world'"


def test_shell_quote_single_quotes():
    assert shell_quote("it's") == "'it'\\''s'"


def test_shell_quote_empty():
    assert shell_quote("") == "''"


def test_strip_existing_resume():
    s = _session(argv=["claude", "--resume", "old-id", "--model", "opus"])
    line = build_resume_line(s)
    assert "old-id" not in line
    assert "--resume test-id" in line
    assert "--model" in line


def test_strip_resume_equals():
    s = _session(argv=["claude", "--resume=old-id"])
    line = build_resume_line(s)
    assert "old-id" not in line
    assert "--resume test-id" in line


def test_ensure_claude_first():
    s = _session(argv=["node", "cli.js"])
    line = build_resume_line(s)
    assert "exec claude" in line
