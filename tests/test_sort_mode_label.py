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
