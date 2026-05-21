from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from tests.tui.tmux_controller import TmuxController
from tests.tui.seed import seed_db, seed_time_spread


def pytest_configure(config):
    for marker, desc in [
        ("tui", "TUI tests requiring tmux"),
        ("smoke", "fast TUI smoke tests"),
        ("regression", "regression tests for known bugs"),
        ("slow", "tests taking > 15 seconds"),
        ("visual", "visual/theme tests"),
        ("stress", "stress and adversarial tests"),
        ("performance", "performance benchmark tests"),
    ]:
        config.addinivalue_line("markers", f"{marker}: {desc}")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tui" in str(item.fspath):
            item.add_marker(pytest.mark.tui)


@pytest.fixture(scope="session", autouse=True)
def _check_tmux():
    if shutil.which("tmux") is None:
        pytest.skip("tmux not installed")


@pytest.fixture(scope="session", autouse=True)
def _cleanup_stale_sessions():
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        for name in result.stdout.strip().split("\n"):
            if name.startswith("seshi-test-"):
                subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
    yield


@pytest.fixture
def tmp_home(tmp_path):
    seshi_dir = tmp_path / ".seshi"
    seshi_dir.mkdir()
    claude_dir = tmp_path / ".claude" / "projects"
    claude_dir.mkdir(parents=True)
    return str(tmp_path)


@pytest.fixture
def db_path(tmp_home):
    return os.path.join(tmp_home, ".seshi", "db.sqlite")


@pytest.fixture
def seeded_db(db_path):
    conn = seed_db(db_path)
    yield conn
    conn.close()


@pytest.fixture
def seeded_db_with_sessions(seeded_db):
    ids = seed_time_spread(seeded_db, count=20)
    return seeded_db, ids


@pytest.fixture
def tmux():
    ctrl = TmuxController()
    ctrl.start()
    yield ctrl
    ctrl.stop()


@pytest.fixture
def tui(tmux, tmp_home, seeded_db_with_sessions):
    conn, session_ids = seeded_db_with_sessions
    conn.close()
    tmux.launch_seshi(tmp_home)
    yield tmux, session_ids


@pytest.fixture
def tui_empty(tmux, tmp_home, seeded_db):
    seeded_db.close()
    tmux.launch_seshi(tmp_home)
    return tmux


@pytest.fixture
def tui_custom(tmux, tmp_home, db_path):
    def _launch(seed_fn, extra_args="", extra_env=""):
        conn = seed_db(db_path)
        result = seed_fn(conn)
        conn.close()
        tmux.launch_seshi(tmp_home, extra_args=extra_args, extra_env=extra_env)
        return tmux, result

    return _launch
