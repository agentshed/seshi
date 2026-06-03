"""Tests for new-session launcher (n/N keys) and directory picker."""
import asyncio
import os
import time
from unittest.mock import patch, MagicMock

from seshi.tui.app import SeshiApp, launch_tui
from seshi.tui.dir_picker import DirPickerScreen


def _insert_session(conn, session_id, cwd, ts=None, frecency_rank=1.0):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, created_at, last_activity_at, frecency_rank)
        VALUES (?,?,?,?,?,?)""",
        (session_id, cwd, "[]", ts, ts, frecency_rank),
    )
    conn.commit()


def test_new_session_cwd(tmp_db):
    """Press n in sessions view -> app.chosen_cwd is set to os.getcwd()."""
    _insert_session(tmp_db, "s1", "/tmp/project-a")

    async def run_case():
        app = SeshiApp(conn=tmp_db)
        async with app.run_test() as pilot:
            await pilot.press("n")

        assert app.chosen_cwd == os.getcwd()
        assert app.chosen_session is None

    asyncio.run(run_case())


def test_dir_picker_sort_cycle(tmp_db):
    """Sort mode cycles frecency -> recency -> frequency and reorders dirs."""
    now = int(time.time())
    _insert_session(tmp_db, "s1", "/tmp/project-a", ts=now - 1000, frecency_rank=10.0)
    _insert_session(tmp_db, "s2", "/tmp/project-b", ts=now, frecency_rank=1.0)

    screen = DirPickerScreen(tmp_db)
    assert screen._sort_mode == "frecency"
    assert screen._dirs[0]["cwd"] == "/tmp/project-a"

    screen._sort_mode = "recency"
    screen._apply_sort()
    assert screen._sort_mode == "recency"
    assert screen._dirs[0]["cwd"] == "/tmp/project-b"

    screen._sort_mode = "frequency"
    screen._apply_sort()
    assert screen._sort_mode == "frequency"


def test_dir_picker_enter_selects(tmp_db):
    """Open dir picker with sessions in multiple cwds, Enter selects."""
    _insert_session(tmp_db, "s1", "/tmp/project-a", frecency_rank=10.0)
    _insert_session(tmp_db, "s2", "/tmp/project-b", frecency_rank=5.0)

    async def run_case():
        app = SeshiApp(conn=tmp_db)
        async with app.run_test() as pilot:
            # Press N to open the dir picker
            await pilot.press("N")
            await pilot.pause()

            # Press Enter to select the first directory
            await pilot.press("enter")
            await pilot.pause()

        assert app.chosen_cwd is not None
        assert app.chosen_session is None

    asyncio.run(run_case())


def test_dir_picker_escape_cancels(tmp_db):
    """Open dir picker -> press Escape -> modal dismissed, no chosen_cwd."""
    _insert_session(tmp_db, "s1", "/tmp/project-a")

    async def run_case():
        app = SeshiApp(conn=tmp_db)
        async with app.run_test() as pilot:
            await pilot.press("N")
            await pilot.pause()

            # Press Escape to cancel
            await pilot.press("escape")
            await pilot.pause()

        assert app.chosen_cwd is None
        assert app.chosen_session is None

    asyncio.run(run_case())


def test_launch_tui_new_session_subprocess(tmp_db, tmp_path):
    """When chosen_cwd is set and chosen_session is None, claude is spawned in the target dir."""
    target_dir = str(tmp_path / "test-project")
    os.makedirs(target_dir, exist_ok=True)

    mock_run = MagicMock()
    chdir_calls = []
    original_chdir = os.chdir
    exit_count = 0

    def patched_run(self_app):
        nonlocal exit_count
        exit_count += 1
        if exit_count == 1:
            self_app.chosen_cwd = target_dir
            self_app.chosen_session = None
        else:
            self_app.chosen_cwd = None
            self_app.chosen_session = None

    def tracking_chdir(path):
        chdir_calls.append(path)
        return original_chdir(path)

    with patch.object(SeshiApp, 'run', patched_run), \
         patch('subprocess.run', mock_run), \
         patch('os.isatty', return_value=True), \
         patch('seshi.tui.app.os.chdir', tracking_chdir):
        launch_tui()

    mock_run.assert_called_once_with(["claude"])
    assert target_dir in chdir_calls


def test_dir_picker_data_source(tmp_db):
    """DirPickerScreen queries grouped session cwds correctly."""
    now = int(time.time())
    _insert_session(tmp_db, "s1", "/tmp/project-a", ts=now - 100, frecency_rank=10.0)
    _insert_session(tmp_db, "s2", "/tmp/project-a", ts=now, frecency_rank=5.0)
    _insert_session(tmp_db, "s3", "/tmp/project-b", ts=now - 200, frecency_rank=3.0)

    screen = DirPickerScreen(tmp_db)

    assert len(screen._dirs) == 2

    # Default sort is frecency (total_frecency descending)
    # project-a has total_frecency 15.0, project-b has 3.0
    assert screen._dirs[0]["cwd"] == "/tmp/project-a"
    assert screen._dirs[0]["count"] == 2
    assert screen._dirs[1]["cwd"] == "/tmp/project-b"
    assert screen._dirs[1]["count"] == 1


def test_dir_picker_render_with_language(tmp_db):
    """Entries with a detected language show a bracketed badge like [py]."""
    now = int(time.time())
    _insert_session(tmp_db, "s1", "/tmp/project-a", ts=now, frecency_rank=5.0)

    screen = DirPickerScreen(tmp_db)

    with patch("seshi.tui.dir_picker.detect_language", return_value="py"):
        rendered = screen._render_content()

    plain = rendered.plain
    assert "[py]" in plain
    assert "1 session" in plain


def test_dir_picker_render_no_language(tmp_db):
    """Entries without a detected language omit the badge but still align."""
    now = int(time.time())
    _insert_session(tmp_db, "s1", "/tmp/project-a", ts=now, frecency_rank=5.0)
    _insert_session(tmp_db, "s2", "/tmp/project-b", ts=now, frecency_rank=3.0)

    screen = DirPickerScreen(tmp_db)

    with patch("seshi.tui.dir_picker.detect_language", return_value=""):
        rendered = screen._render_content()

    plain = rendered.plain
    # No brackets should appear when language is empty
    assert "[" not in plain.split("choose directory")[1].split("Enter")[0]
    # Both entries should still show session counts
    assert plain.count("session") >= 2


def test_dir_picker_render_long_path(tmp_db):
    """Long paths don't prevent metadata columns from rendering."""
    now = int(time.time())
    long_path = "/tmp/" + "a" * 60 + "/project"
    short_path = "/tmp/b"
    _insert_session(tmp_db, "s1", long_path, ts=now, frecency_rank=5.0)
    _insert_session(tmp_db, "s2", short_path, ts=now - 100, frecency_rank=3.0)

    screen = DirPickerScreen(tmp_db)

    with patch("seshi.tui.dir_picker.detect_language", return_value="py"):
        rendered = screen._render_content()

    plain = rendered.plain
    # Both entries should show badge and session count (filter out header)
    body = plain.split("choose directory")[1].split("Enter")[0]
    lines = [l for l in body.split("\n") if "session" in l]
    assert len(lines) == 2
    for line in lines:
        assert "[py]" in line
        assert "session" in line


def test_dir_picker_render_column_alignment(tmp_db):
    """Session count column aligns vertically across entries."""
    now = int(time.time())
    # Insert 12 sessions for /tmp/short so count strings differ in length
    # ("12 sessions" vs "1 session") and rjust alignment is actually exercised.
    for i in range(12):
        _insert_session(tmp_db, f"s1-{i}", "/tmp/short", ts=now, frecency_rank=5.0)
    _insert_session(tmp_db, "s2", "/tmp/much-longer-path", ts=now, frecency_rank=3.0)

    screen = DirPickerScreen(tmp_db)

    with patch("seshi.tui.dir_picker.detect_language", return_value=""):
        rendered = screen._render_content()

    plain = rendered.plain
    body = plain.split("choose directory")[1].split("Enter")[0]
    lines = [l for l in body.split("\n") if "session" in l]
    assert len(lines) == 2
    # Count strings differ in length ("12 sessions" vs "1 session"),
    # so alignment is only correct if rjust is working.
    assert "12 sessions" in lines[0]
    assert "1 session" in lines[1]
    # The count column should end at the same position (right-justified).
    # Find where "sessions" / "session" ends in each line.
    import re
    ends = []
    for l in lines:
        m = re.search(r"\d+ sessions?", l)
        assert m is not None
        ends.append(m.end())
    assert ends[0] == ends[1]
