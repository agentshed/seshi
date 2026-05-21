import asyncio

from seshi.tui.app import SeshiApp
from seshi.tui.search_bar import SearchBar


def test_sort_mode_label_updates_after_cycle(tmp_db):
    async def run_case():
        app = SeshiApp(conn=tmp_db)
        async with app.run_test() as pilot:
            search = app.query_one(SearchBar)
            assert search.sort_mode == "frecency"

            await pilot.press("s")

            assert app._sessions_list.sort_mode == "recency"
            assert search.sort_mode == "recency"

    asyncio.run(run_case())


def test_hide_missing_dirs_updates_search_counts(tmp_db, tmp_path):
    existing = tmp_path / "existing-project"
    existing.mkdir()
    missing = tmp_path / "missing-project"
    tmp_db.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, created_at, last_activity_at)
        VALUES (?, ?, '[]', ?, ?)""",
        ("existing-session", str(existing), 1, 1),
    )
    tmp_db.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, created_at, last_activity_at)
        VALUES (?, ?, '[]', ?, ?)""",
        ("missing-session", str(missing), 2, 2),
    )
    tmp_db.commit()

    async def run_case():
        app = SeshiApp(conn=tmp_db)
        async with app.run_test() as pilot:
            search = app.query_one(SearchBar)
            assert len(app._sessions_list.sessions) == 2
            assert search.shown == 2

            await pilot.press("H")

            assert len(app._sessions_list.sessions) == 1
            assert search.shown == 1
            assert search.total == 1

    asyncio.run(run_case())
