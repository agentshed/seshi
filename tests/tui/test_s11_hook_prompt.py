import os
import time

import pytest

from tests.tui.assertions import assert_header_visible
from tests.tui.seed import seed_db, seed_time_spread


@pytest.fixture
def tmp_home_stale_hook(tmp_path):
    """tmp_home with a stale hook.sh to trigger the update prompt."""
    seshi_dir = tmp_path / ".seshi"
    seshi_dir.mkdir()
    (seshi_dir / "hook.sh").write_text("#!/bin/bash\n# old version\n")
    os.chmod(str(seshi_dir / "hook.sh"), 0o755)
    claude_dir = tmp_path / ".claude" / "projects"
    claude_dir.mkdir(parents=True)
    return str(tmp_path)


@pytest.fixture
def tmp_home_no_hook(tmp_path):
    """tmp_home with no hook.sh to trigger the install prompt."""
    seshi_dir = tmp_path / ".seshi"
    seshi_dir.mkdir()
    claude_dir = tmp_path / ".claude" / "projects"
    claude_dir.mkdir(parents=True)
    return str(tmp_path)


@pytest.mark.smoke
@pytest.mark.timeout(30)
class TestHookPrompt:

    def test_stale_hook_prompt_accept(self, tmux, tmp_home_stale_hook):
        db_path = os.path.join(tmp_home_stale_hook, ".seshi", "db.sqlite")
        conn = seed_db(db_path)
        seed_time_spread(conn, count=3)
        conn.close()

        path = os.environ.get("PATH", "")
        tmux.send_keys(f"export PATH='{path}'", "Enter")
        time.sleep(0.2)
        tmux.send_keys(f"HOME={tmp_home_stale_hook} uv run seshi", "Enter")

        tmux.wait_for("Install now?", timeout=10)
        screen = tmux.capture()
        assert "outdated" in screen.raw

        tmux.send_keys("y", "Enter")
        tmux.wait_for_tui(timeout=15)
        screen = tmux.capture()
        assert_header_visible(screen)

        hook_path = os.path.join(tmp_home_stale_hook, ".seshi", "hook.sh")
        content = open(hook_path).read()
        assert "old version" not in content

    def test_missing_hook_prompt_accept(self, tmux, tmp_home_no_hook):
        db_path = os.path.join(tmp_home_no_hook, ".seshi", "db.sqlite")
        conn = seed_db(db_path)
        seed_time_spread(conn, count=3)
        conn.close()

        path = os.environ.get("PATH", "")
        tmux.send_keys(f"export PATH='{path}'", "Enter")
        time.sleep(0.2)
        tmux.send_keys(f"HOME={tmp_home_no_hook} uv run seshi", "Enter")

        tmux.wait_for("Install now?", timeout=10)
        screen = tmux.capture()
        assert "not installed" in screen.raw

        tmux.send_keys("y", "Enter")
        tmux.wait_for_tui(timeout=15)
        screen = tmux.capture()
        assert_header_visible(screen)

        hook_path = os.path.join(tmp_home_no_hook, ".seshi", "hook.sh")
        assert os.path.exists(hook_path)

    def test_hook_prompt_decline_still_launches(self, tmux, tmp_home_stale_hook):
        db_path = os.path.join(tmp_home_stale_hook, ".seshi", "db.sqlite")
        conn = seed_db(db_path)
        seed_time_spread(conn, count=3)
        conn.close()

        path = os.environ.get("PATH", "")
        tmux.send_keys(f"export PATH='{path}'", "Enter")
        time.sleep(0.2)
        tmux.send_keys(f"HOME={tmp_home_stale_hook} uv run seshi", "Enter")

        tmux.wait_for("Install now?", timeout=10)
        tmux.send_keys("n", "Enter")
        tmux.wait_for_tui(timeout=15)
        screen = tmux.capture()
        assert_header_visible(screen)

        hook_path = os.path.join(tmp_home_stale_hook, ".seshi", "hook.sh")
        content = open(hook_path).read()
        assert "old version" in content
