"""Tests for CLI query routing: `seshi <query>` opens TUI with search."""

from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from seshi.cli import main
from seshi.db import init_schema


def _setup_db(tmp_path: Path) -> Path:
    db_path = tmp_path / ".seshi" / "db.sqlite"
    db_path.parent.mkdir(parents=True)
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    conn.close()
    return db_path


def _invoke_with_mocked_tui(tmp_path, args):
    db_path = _setup_db(tmp_path)
    runner = CliRunner()
    with mock.patch("seshi.cli.DB_PATH", db_path), \
         mock.patch("seshi.db.DB_PATH", db_path), \
         mock.patch("seshi.cli.drain_queue"), \
         mock.patch("seshi.tui.app.launch_tui") as mock_launch:
        result = runner.invoke(main, args)
    return result, mock_launch


class TestQueryRoutesToTui:

    def test_single_word_query(self, tmp_path):
        result, mock_launch = _invoke_with_mocked_tui(tmp_path, ["auth"])
        mock_launch.assert_called_once()
        assert mock_launch.call_args[0][0]["search_query"] == "auth"

    def test_multi_word_query(self, tmp_path):
        result, mock_launch = _invoke_with_mocked_tui(tmp_path, ["fix", "auth"])
        mock_launch.assert_called_once()
        assert mock_launch.call_args[0][0]["search_query"] == "fix auth"

    def test_here_flag_with_query(self, tmp_path):
        result, mock_launch = _invoke_with_mocked_tui(tmp_path, ["--here", "auth"])
        mock_launch.assert_called_once()
        ctx_obj = mock_launch.call_args[0][0]
        assert ctx_obj["search_query"] == "auth"
        assert ctx_obj["here_cwd"] is not None

    def test_no_args_launches_tui_without_search(self, tmp_path):
        result, mock_launch = _invoke_with_mocked_tui(tmp_path, [])
        mock_launch.assert_called_once()
        assert "search_query" not in mock_launch.call_args[0][0]


class TestKnownSubcommandsUnaffected:

    def test_list_command_dispatches_normally(self, tmp_path):
        result, mock_launch = _invoke_with_mocked_tui(tmp_path, ["list"])
        mock_launch.assert_not_called()
        assert result.exit_code == 0

    def test_resume_command_still_works(self, tmp_path):
        result, mock_launch = _invoke_with_mocked_tui(tmp_path, ["resume", "foo"])
        mock_launch.assert_not_called()

    def test_dash_prefix_not_treated_as_query(self, tmp_path):
        result, mock_launch = _invoke_with_mocked_tui(tmp_path, ["--unknown-flag"])
        mock_launch.assert_not_called()
        assert result.exit_code != 0


class TestEdgeCases:

    def test_subcommand_prefix_routes_to_tui(self, tmp_path):
        result, mock_launch = _invoke_with_mocked_tui(tmp_path, ["lis"])
        mock_launch.assert_called_once()
        assert mock_launch.call_args[0][0]["search_query"] == "lis"
