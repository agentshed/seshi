"""Regression tests for CLI flag handling."""

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


@pytest.mark.regression
class TestHereFlag:
    """Bug #67: --here flag rejected when placed after subcommand."""

    def test_here_before_subcommand_accepted(self, tmp_path):
        """Baseline: seshi --here list should work."""
        db_path = _setup_db(tmp_path)
        runner = CliRunner()
        with mock.patch("seshi.cli.DB_PATH", db_path), \
             mock.patch("seshi.db.DB_PATH", db_path), \
             mock.patch("seshi.cli.drain_queue"):
            result = runner.invoke(main, ["--here", "list"])
        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_here_after_subcommand_accepted(self, tmp_path):
        """seshi list --here should also work.

        Bug #67: currently fails with 'No such option: --here' because
        --here is defined on the Click group, not on subcommands.
        """
        db_path = _setup_db(tmp_path)
        runner = CliRunner()
        with mock.patch("seshi.cli.DB_PATH", db_path), \
             mock.patch("seshi.db.DB_PATH", db_path), \
             mock.patch("seshi.cli.drain_queue"):
            result = runner.invoke(main, ["list", "--here"])
        assert result.exit_code == 0, (
            f"'seshi list --here' should be accepted but got "
            f"exit_code={result.exit_code}: {result.output}"
        )
        assert "No such option" not in result.output
