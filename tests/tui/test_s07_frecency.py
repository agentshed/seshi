import time

import pytest

from tests.tui.assertions import (
    assert_screen_contains,
    assert_session_visible,
    assert_session_not_visible,
    assert_sort_mode,
)
from tests.tui.seed import insert_session


def seed_for_frecency(conn):
    now = int(time.time())
    sessions = {}

    sessions["heavy"] = insert_session(
        conn,
        custom_name="heavy-project",
        first_prompt="Heavily resumed project work",
        cwd="/tmp/heavy",
        last_activity_at=now - 3 * 86400,
    )
    conn.execute(
        "UPDATE sessions SET resume_count = 15, frecency_rank = 15.0 WHERE session_id = ?",
        (sessions["heavy"],),
    )

    sessions["light"] = insert_session(
        conn,
        custom_name="light-project",
        first_prompt="Brand new session",
        cwd="/tmp/light",
        last_activity_at=now - 1800,
    )

    sessions["mid"] = insert_session(
        conn,
        custom_name="mid-project",
        first_prompt="Moderately used project",
        cwd="/tmp/mid",
        last_activity_at=now - 6 * 3600,
    )
    conn.execute(
        "UPDATE sessions SET resume_count = 5, frecency_rank = 5.0 WHERE session_id = ?",
        (sessions["mid"],),
    )

    conn.commit()
    return sessions


@pytest.mark.smoke
class TestFrecencyDefaultSort:

    def test_frecency_default_sort_order(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_frecency)
        screen = ctrl.capture()
        assert_session_visible(screen, "heavy-project")
        assert_session_visible(screen, "light-project")
        heavy_line = None
        light_line = None
        for i, line in enumerate(screen.lines):
            if "heavy-project" in line and heavy_line is None:
                heavy_line = i
            if "light-project" in line and light_line is None:
                light_line = i
        assert heavy_line is not None and light_line is not None
        assert heavy_line < light_line, (
            f"heavy-project (line {heavy_line}) should appear above "
            f"light-project (line {light_line})"
        )


class TestFrecencyFrequencySort:

    def test_frequency_sort_uses_resume_count(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_frecency)
        ctrl.send_keys("s")
        time.sleep(0.3)
        ctrl.send_keys("s")
        time.sleep(0.5)
        screen = ctrl.capture()
        assert_sort_mode(screen, "frequency")
        heavy_line = None
        light_line = None
        for i, line in enumerate(screen.lines):
            if "heavy-project" in line and heavy_line is None:
                heavy_line = i
            if "light-project" in line and light_line is None:
                light_line = i
        assert heavy_line is not None and light_line is not None
        assert heavy_line < light_line


def seed_for_aging(conn):
    now = int(time.time())
    sessions = {}

    sessions["decayed"] = insert_session(
        conn,
        custom_name="decayed-session",
        first_prompt="This will be auto-archived",
        cwd="/tmp/decayed",
        last_activity_at=now - 86400,
    )
    conn.execute(
        "UPDATE sessions SET frecency_rank = 0.5 WHERE session_id = ?",
        (sessions["decayed"],),
    )

    for i in range(50):
        sid = insert_session(
            conn,
            first_prompt=f"High rank session {i}",
            cwd=f"/tmp/high-{i}",
            last_activity_at=now - 3600,
        )
        conn.execute(
            "UPDATE sessions SET frecency_rank = 25.0 WHERE session_id = ?",
            (sid,),
        )

    conn.commit()
    return sessions


class TestFrecencyAging:

    def test_aging_auto_archives_decayed_session(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_aging)
        screen = ctrl.capture()
        assert_session_not_visible(screen, "decayed-session")


def seed_for_aging_protected(conn):
    now = int(time.time())
    sessions = {}

    sessions["fav_decayed"] = insert_session(
        conn,
        custom_name="fav-decayed",
        first_prompt="Favorited but low rank",
        cwd="/tmp/fav-decayed",
        is_favorite=1,
        last_activity_at=now - 86400,
    )
    conn.execute(
        "UPDATE sessions SET frecency_rank = 0.5 WHERE session_id = ?",
        (sessions["fav_decayed"],),
    )

    for i in range(50):
        sid = insert_session(
            conn,
            first_prompt=f"High rank session {i}",
            cwd=f"/tmp/high-{i}",
            last_activity_at=now - 3600,
        )
        conn.execute(
            "UPDATE sessions SET frecency_rank = 25.0 WHERE session_id = ?",
            (sid,),
        )

    conn.commit()
    return sessions


class TestFrecencyAgingProtection:

    def test_aging_protects_favorite_from_archive(self, tui_custom):
        ctrl, sessions = tui_custom(seed_for_aging_protected)
        screen = ctrl.capture()
        assert_session_visible(screen, "fav-decayed")
