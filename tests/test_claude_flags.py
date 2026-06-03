"""Tests for persistent Claude Code CLI flag defaults."""

import json
from unittest import mock

from click.testing import CliRunner

from seshi.claude_flags import (
    DEFAULTS,
    build_args,
    get_flags,
    reset_flags,
    seed_defaults,
    set_flag,
    unset_flag,
)
from seshi.resume import build_resume_line
from seshi.models import Session


def _session(cwd="/home/user", argv=None, session_id="test-id"):
    argv_json = json.dumps(argv or ["claude"])
    return Session(
        session_id=session_id, cwd=cwd, launch_argv_json=argv_json,
        env_json=None, git_branch=None, git_sha=None, first_prompt=None,
        custom_name=None, ai_title=None, is_favorite=0, is_archived=0,
        is_backfilled=0, message_count=0, token_count=0, status=None,
        created_at=1000, last_activity_at=1000, origin_host=None,
        schema_version=1,
    )


# -- core logic tests --


def test_set_flag_stores_value(tmp_db):
    set_flag(tmp_db, "model", "opus")
    row = tmp_db.execute(
        "SELECT value FROM settings WHERE key = 'claude.model'"
    ).fetchone()
    assert row is not None
    assert row["value"] == "opus"


def test_get_flags_returns_all(tmp_db):
    # Clear any seeded defaults first
    tmp_db.execute("DELETE FROM settings WHERE key LIKE 'claude.%'")
    tmp_db.commit()
    set_flag(tmp_db, "model", "opus")
    set_flag(tmp_db, "effort", "high")
    flags = get_flags(tmp_db)
    assert flags == {"model": "opus", "effort": "high"}


def test_unset_flag_removes(tmp_db):
    set_flag(tmp_db, "model", "opus")
    unset_flag(tmp_db, "model")
    flags = get_flags(tmp_db)
    assert "model" not in flags


def test_reset_single_flag_to_default(tmp_db):
    set_flag(tmp_db, "effort", "low")
    reset_flags(tmp_db, "effort")
    flags = get_flags(tmp_db)
    assert flags["effort"] == DEFAULTS["effort"]


def test_reset_single_flag_no_default(tmp_db):
    set_flag(tmp_db, "model", "opus")
    reset_flags(tmp_db, "model")
    flags = get_flags(tmp_db)
    assert "model" not in flags


def test_reset_all_flags(tmp_db):
    set_flag(tmp_db, "model", "opus")
    set_flag(tmp_db, "effort", "low")
    reset_flags(tmp_db)
    flags = get_flags(tmp_db)
    # Only defaults should remain
    assert "model" not in flags
    for k, v in DEFAULTS.items():
        assert flags[k] == v


def test_build_args_boolean(tmp_db):
    tmp_db.execute("DELETE FROM settings WHERE key LIKE 'claude.%'")
    tmp_db.commit()
    set_flag(tmp_db, "worktree", "true")
    assert build_args(tmp_db) == ["--worktree"]


def test_build_args_value(tmp_db):
    tmp_db.execute("DELETE FROM settings WHERE key LIKE 'claude.%'")
    tmp_db.commit()
    set_flag(tmp_db, "effort", "high")
    assert build_args(tmp_db) == ["--effort", "high"]


def test_build_args_comma_separated(tmp_db):
    tmp_db.execute("DELETE FROM settings WHERE key LIKE 'claude.%'")
    tmp_db.commit()
    set_flag(tmp_db, "add-dir", "a,b")
    assert build_args(tmp_db) == ["--add-dir", "a", "--add-dir", "b"]


def test_build_args_empty(tmp_db):
    tmp_db.execute("DELETE FROM settings WHERE key LIKE 'claude.%'")
    tmp_db.commit()
    assert build_args(tmp_db) == []


def test_seed_defaults(tmp_db):
    tmp_db.execute("DELETE FROM settings WHERE key LIKE 'claude.%'")
    tmp_db.commit()
    seed_defaults(tmp_db)
    flags = get_flags(tmp_db)
    for k, v in DEFAULTS.items():
        assert flags[k] == v


# -- build_resume_line integration --


def test_build_resume_line_with_flags(tmp_db):
    tmp_db.execute("DELETE FROM settings WHERE key LIKE 'claude.%'")
    tmp_db.commit()
    set_flag(tmp_db, "effort", "high")
    s = _session()
    line = build_resume_line(s, conn=tmp_db)
    assert "--effort high" in line
    assert line.index("--effort") < line.index("--resume")


def test_build_resume_line_without_conn():
    """Without conn, build_resume_line works as before (no flags)."""
    s = _session()
    line = build_resume_line(s)
    assert "--resume test-id" in line
    # Should not contain any flag args beyond what's in argv
    assert "--effort" not in line


# -- CLI integration tests --


def _setup_db(tmp_path):
    from pathlib import Path
    import sqlite3
    from seshi.db import init_schema

    db_path = tmp_path / ".seshi" / "db.sqlite"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    conn.close()
    return db_path


def test_set_cmd_cli(tmp_path):
    from seshi.cli import main

    db_path = _setup_db(tmp_path)
    runner = CliRunner()
    with mock.patch("seshi.cli.DB_PATH", db_path), \
         mock.patch("seshi.db.DB_PATH", db_path), \
         mock.patch("seshi.cli.drain_queue"):
        result = runner.invoke(main, ["set", "model", "opus"])
    assert result.exit_code == 0, f"Failed: {result.output}"
    assert "model = opus" in result.output


def test_unset_cmd_cli(tmp_path):
    from seshi.cli import main

    db_path = _setup_db(tmp_path)
    runner = CliRunner()
    with mock.patch("seshi.cli.DB_PATH", db_path), \
         mock.patch("seshi.db.DB_PATH", db_path), \
         mock.patch("seshi.cli.drain_queue"):
        runner.invoke(main, ["set", "model", "opus"])
        result = runner.invoke(main, ["unset", "model"])
    assert result.exit_code == 0, f"Failed: {result.output}"
    assert "unset model" in result.output


def test_set_no_args_lists(tmp_path):
    from seshi.cli import main

    db_path = _setup_db(tmp_path)
    runner = CliRunner()
    with mock.patch("seshi.cli.DB_PATH", db_path), \
         mock.patch("seshi.db.DB_PATH", db_path), \
         mock.patch("seshi.cli.drain_queue"):
        runner.invoke(main, ["set", "model", "opus"])
        result = runner.invoke(main, ["set"])
    assert result.exit_code == 0, f"Failed: {result.output}"
    assert "model = opus" in result.output


def test_set_preview(tmp_path):
    from seshi.cli import main

    db_path = _setup_db(tmp_path)
    runner = CliRunner()
    with mock.patch("seshi.cli.DB_PATH", db_path), \
         mock.patch("seshi.db.DB_PATH", db_path), \
         mock.patch("seshi.cli.drain_queue"):
        # Clear defaults, set specific flags
        runner.invoke(main, ["set", "--reset"])
        runner.invoke(main, ["set", "model", "opus"])
        result = runner.invoke(main, ["set", "--preview"])
    assert result.exit_code == 0, f"Failed: {result.output}"
    assert "--model opus" in result.output


def test_set_boolean_flag(tmp_path):
    from seshi.cli import main

    db_path = _setup_db(tmp_path)
    runner = CliRunner()
    with mock.patch("seshi.cli.DB_PATH", db_path), \
         mock.patch("seshi.db.DB_PATH", db_path), \
         mock.patch("seshi.cli.drain_queue"):
        result = runner.invoke(main, ["set", "worktree"])
    assert result.exit_code == 0, f"Failed: {result.output}"
    assert "worktree = true" in result.output
