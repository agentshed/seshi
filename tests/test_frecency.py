import asyncio
import time

from seshi.models import Session
from seshi.search import (
    _recency_multiplier,
    age_frecency_ranks,
    frecency_score,
    list_sessions,
    rank_sessions,
    AGING_THRESHOLD,
)


def _make_session(
    session_id="s1",
    cwd="/tmp/proj",
    last_activity_at=None,
    frecency_rank=1.0,
    resume_count=0,
    is_favorite=0,
    is_archived=0,
    custom_name=None,
    first_prompt=None,
):
    now = int(time.time())
    lat = last_activity_at if last_activity_at is not None else now
    return Session(
        session_id=session_id,
        cwd=cwd,
        launch_argv_json="[]",
        env_json=None,
        git_branch=None,
        git_sha=None,
        first_prompt=first_prompt,
        custom_name=custom_name,
        is_favorite=is_favorite,
        is_archived=is_archived,
        is_backfilled=0,
        message_count=0,
        token_count=0,
        status=None,
        created_at=lat,
        last_activity_at=lat,
        origin_host=None,
        schema_version=1,
        resume_count=resume_count,
        frecency_rank=frecency_rank,
    )


def _insert_session(conn, session_id, cwd="/home", custom_name=None,
                     first_prompt=None, is_favorite=0, ts=None,
                     frecency_rank=1.0, resume_count=0, is_archived=0):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, custom_name, first_prompt,
         is_favorite, is_archived, created_at, last_activity_at,
         frecency_rank, resume_count)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (session_id, cwd, "[]", custom_name, first_prompt,
         is_favorite, is_archived, ts, ts, frecency_rank, resume_count),
    )
    conn.commit()


# --- Step-function bucket tests ---

class TestRecencyMultiplier:

    def test_buckets(self):
        assert _recency_multiplier(0) == 4.0
        assert _recency_multiplier(2) == 4.0
        assert _recency_multiplier(3.99) == 4.0
        assert _recency_multiplier(5) == 2.0
        assert _recency_multiplier(23.99) == 2.0
        assert _recency_multiplier(48) == 1.0
        assert _recency_multiplier(24 * 6.99) == 1.0
        assert _recency_multiplier(24 * 14) == 0.5
        assert _recency_multiplier(24 * 27.99) == 0.5
        assert _recency_multiplier(24 * 30) == 0.25
        assert _recency_multiplier(24 * 365) == 0.25

    def test_boundary_exact(self):
        assert _recency_multiplier(4) == 2.0
        assert _recency_multiplier(24) == 1.0
        assert _recency_multiplier(24 * 7) == 0.5
        assert _recency_multiplier(24 * 28) == 0.25


# --- Multiplicative blending tests ---

class TestFrecencyScore:

    def test_rank_amplifies(self):
        now = int(time.time())
        s1 = _make_session(last_activity_at=now - 3600, frecency_rank=1.0)
        s10 = _make_session(last_activity_at=now - 3600, frecency_rank=10.0)
        assert frecency_score(s10, now) == 10 * frecency_score(s1, now)

    def test_high_rank_old_beats_low_rank_new(self):
        now = int(time.time())
        old_heavy = _make_session(last_activity_at=now - 14 * 86400, frecency_rank=10.0)
        new_light = _make_session(last_activity_at=now - 3600, frecency_rank=1.0)
        assert frecency_score(old_heavy, now) > frecency_score(new_light, now)

    def test_new_session_default_rank(self):
        now = int(time.time())
        s = _make_session(last_activity_at=now - 1800, frecency_rank=1.0)
        assert frecency_score(s, now) == 4.0

    def test_zero_age(self):
        now = int(time.time())
        s = _make_session(last_activity_at=now, frecency_rank=3.0)
        assert frecency_score(s, now) == 12.0

    def test_very_old(self):
        now = int(time.time())
        s = _make_session(last_activity_at=now - 365 * 86400, frecency_rank=2.0)
        assert frecency_score(s, now) == 0.5


# --- Search integration tests ---

class TestRankSessionsFrecencyBlend:

    def test_frecency_boosts_ties(self, tmp_db):
        now = int(time.time())
        _insert_session(tmp_db, "id-high", custom_name="auth-rewrite",
                        ts=now - 3600, frecency_rank=10.0)
        _insert_session(tmp_db, "id-low", custom_name="auth-bugfix",
                        ts=now - 3600, frecency_rank=1.0)
        results = rank_sessions(tmp_db, "auth")
        assert len(results) >= 2
        assert results[0][0].session_id == "id-high"

    def test_fuzzy_still_dominates(self, tmp_db):
        now = int(time.time())
        _insert_session(tmp_db, "id-exact", custom_name="authentication",
                        ts=now - 86400, frecency_rank=1.0)
        _insert_session(tmp_db, "id-weak", first_prompt="unrelated work",
                        cwd="/tmp/auth-adjacent",
                        ts=now - 100, frecency_rank=50.0)
        results = rank_sessions(tmp_db, "authentication")
        assert results[0][0].session_id == "id-exact"

    def test_no_results_returns_empty(self, tmp_db):
        _insert_session(tmp_db, "id-1", custom_name="something")
        results = rank_sessions(tmp_db, "zzzznonexistent")
        assert results == []


# --- Aging tests ---

class TestAgeFrecencyRanks:

    def test_scales_down_when_over_threshold(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            "seshi.transcript.get_existing_session_ids",
            lambda: {f"id-{i}" for i in range(100)},
        )
        now = int(time.time())
        for i in range(100):
            _insert_session(tmp_db, f"id-{i}", ts=now, frecency_rank=20.0)
        row = tmp_db.execute("SELECT SUM(frecency_rank) as total FROM sessions").fetchone()
        assert row["total"] == 2000.0

        age_frecency_ranks(tmp_db)

        row = tmp_db.execute("SELECT SUM(frecency_rank) as total FROM sessions WHERE is_archived = 0").fetchone()
        assert row["total"] < AGING_THRESHOLD

    def test_noop_under_threshold(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            "seshi.transcript.get_existing_session_ids",
            lambda: {f"id-{i}" for i in range(5)},
        )
        now = int(time.time())
        for i in range(5):
            _insert_session(tmp_db, f"id-{i}", ts=now, frecency_rank=1.0)

        age_frecency_ranks(tmp_db)

        row = tmp_db.execute("SELECT SUM(frecency_rank) as total FROM sessions").fetchone()
        assert row["total"] == 5.0

    def test_archives_low_rank(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            "seshi.transcript.get_existing_session_ids",
            lambda: {"id-low", "id-high"},
        )
        now = int(time.time())
        _insert_session(tmp_db, "id-low", ts=now, frecency_rank=0.01)
        _insert_session(tmp_db, "id-high", ts=now, frecency_rank=1500.0)

        age_frecency_ranks(tmp_db)

        row = tmp_db.execute("SELECT is_archived FROM sessions WHERE session_id = 'id-low'").fetchone()
        assert row["is_archived"] == 1

    def test_protects_favorites(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            "seshi.transcript.get_existing_session_ids",
            lambda: {"id-fav", "id-high"},
        )
        now = int(time.time())
        _insert_session(tmp_db, "id-fav", ts=now, frecency_rank=0.01, is_favorite=1)
        _insert_session(tmp_db, "id-high", ts=now, frecency_rank=1500.0)

        age_frecency_ranks(tmp_db)

        row = tmp_db.execute("SELECT is_archived FROM sessions WHERE session_id = 'id-fav'").fetchone()
        assert row["is_archived"] == 0

    def test_protects_named(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            "seshi.transcript.get_existing_session_ids",
            lambda: {"id-named", "id-high"},
        )
        now = int(time.time())
        _insert_session(tmp_db, "id-named", ts=now, frecency_rank=0.01, custom_name="keep-me")
        _insert_session(tmp_db, "id-high", ts=now, frecency_rank=1500.0)

        age_frecency_ranks(tmp_db)

        row = tmp_db.execute("SELECT is_archived FROM sessions WHERE session_id = 'id-named'").fetchone()
        assert row["is_archived"] == 0

    def test_protects_tagged(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            "seshi.transcript.get_existing_session_ids",
            lambda: {"id-tagged", "id-high"},
        )
        now = int(time.time())
        _insert_session(tmp_db, "id-tagged", ts=now, frecency_rank=0.01)
        tmp_db.execute("INSERT INTO tags (session_id, tag) VALUES (?, ?)", ("id-tagged", "important"))
        tmp_db.commit()
        _insert_session(tmp_db, "id-high", ts=now, frecency_rank=1500.0)

        age_frecency_ranks(tmp_db)

        row = tmp_db.execute("SELECT is_archived FROM sessions WHERE session_id = 'id-tagged'").fetchone()
        assert row["is_archived"] == 0

    def test_excludes_archived_from_sum(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            "seshi.transcript.get_existing_session_ids",
            lambda: {"id-archived", "id-active"},
        )
        now = int(time.time())
        _insert_session(tmp_db, "id-archived", ts=now, frecency_rank=5000.0, is_archived=1)
        _insert_session(tmp_db, "id-active", ts=now, frecency_rank=5.0)

        age_frecency_ranks(tmp_db)

        row = tmp_db.execute("SELECT frecency_rank FROM sessions WHERE session_id = 'id-active'").fetchone()
        assert row["frecency_rank"] == 5.0

    def test_skips_when_recently_aged(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            "seshi.transcript.get_existing_session_ids",
            lambda: {"id-1"},
        )
        now = int(time.time())
        _insert_session(tmp_db, "id-1", ts=now, frecency_rank=2000.0)

        age_frecency_ranks(tmp_db)
        row = tmp_db.execute("SELECT frecency_rank FROM sessions WHERE session_id = 'id-1'").fetchone()
        aged_rank = row["frecency_rank"]
        assert aged_rank < 2000.0

        tmp_db.execute("UPDATE sessions SET frecency_rank = 2000.0 WHERE session_id = 'id-1'")
        tmp_db.commit()
        age_frecency_ranks(tmp_db)
        row = tmp_db.execute("SELECT frecency_rank FROM sessions WHERE session_id = 'id-1'").fetchone()
        assert row["frecency_rank"] == 2000.0

    def test_stale_sessions_excluded_from_sum(self, tmp_db, monkeypatch):
        monkeypatch.setattr(
            "seshi.transcript.get_existing_session_ids",
            lambda: {"id-live"},
        )
        now = int(time.time())
        _insert_session(tmp_db, "id-stale", ts=now, frecency_rank=5000.0)
        _insert_session(tmp_db, "id-live", ts=now, frecency_rank=5.0)

        age_frecency_ranks(tmp_db)

        row = tmp_db.execute("SELECT frecency_rank FROM sessions WHERE session_id = 'id-live'").fetchone()
        assert row["frecency_rank"] == 5.0
        row = tmp_db.execute("SELECT frecency_rank FROM sessions WHERE session_id = 'id-stale'").fetchone()
        assert row["frecency_rank"] == 5000.0


# --- Frequency sort mode ---

class TestFrequencySortMode:

    def test_uses_resume_count(self, tmp_db):
        now = int(time.time())
        _insert_session(tmp_db, "id-few", ts=now, resume_count=2)
        _insert_session(tmp_db, "id-many", ts=now - 3600, resume_count=20)
        sessions = list_sessions(tmp_db, sort_mode="frequency")
        ids = [s.session_id for s in sessions]
        assert ids.index("id-many") < ids.index("id-few")


# --- Schema migration ---

class TestSchemaMigration:

    def test_columns_exist(self, tmp_db):
        cols = [r[1] for r in tmp_db.execute("PRAGMA table_info(sessions)").fetchall()]
        assert "resume_count" in cols
        assert "frecency_rank" in cols

    def test_default_values(self, tmp_db):
        now = int(time.time())
        tmp_db.execute(
            """INSERT INTO sessions
            (session_id, cwd, launch_argv_json, created_at, last_activity_at)
            VALUES (?,?,?,?,?)""",
            ("test-id", "/tmp", "[]", now, now),
        )
        tmp_db.commit()
        row = tmp_db.execute("SELECT resume_count, frecency_rank FROM sessions WHERE session_id = 'test-id'").fetchone()
        assert row["resume_count"] == 0
        assert row["frecency_rank"] == 1.0


# --- Edge cases ---

class TestEdgeCases:

    def test_resume_count_increments(self, tmp_db):
        from seshi.db import record_resume
        now = int(time.time())
        _insert_session(tmp_db, "id-1", ts=now)
        record_resume(tmp_db, "id-1")
        record_resume(tmp_db, "id-1")
        row = tmp_db.execute("SELECT resume_count, frecency_rank FROM sessions WHERE session_id = 'id-1'").fetchone()
        assert row["resume_count"] == 2
        assert row["frecency_rank"] == 3.0

    def test_frecency_rank_default_on_drain(self, tmp_db):
        now = int(time.time())
        tmp_db.execute(
            """INSERT INTO sessions
            (session_id, cwd, launch_argv_json, created_at, last_activity_at)
            VALUES (?,?,?,?,?)""",
            ("drain-id", "/tmp/drain", "[]", now, now),
        )
        tmp_db.commit()
        s = Session.from_row(
            tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'drain-id'").fetchone()
        )
        assert s.frecency_rank == 1.0
        assert s.resume_count == 0


# --- Textual async TUI tests ---

class TestTUIFrecency:

    def test_frecency_sort_order(self, tmp_db):
        from seshi.tui.app import SeshiApp

        now = int(time.time())
        _insert_session(tmp_db, "id-old-heavy", custom_name="heavy-project",
                        ts=now - 3 * 86400, frecency_rank=15.0)
        _insert_session(tmp_db, "id-recent-light", custom_name="light-project",
                        ts=now - 1800, frecency_rank=1.0)
        _insert_session(tmp_db, "id-mid", custom_name="mid-project",
                        ts=now - 6 * 3600, frecency_rank=5.0)

        async def run_case():
            app = SeshiApp(conn=tmp_db)
            async with app.run_test():
                sessions = app._sessions_list.sessions
                names = [s.custom_name for s in sessions]
                assert names.index("heavy-project") < names.index("light-project")
                assert names.index("mid-project") < names.index("light-project")

        asyncio.run(run_case())

    def test_sort_cycle_still_works(self, tmp_db):
        from seshi.tui.app import SeshiApp
        from seshi.tui.search_bar import SearchBar

        async def run_case():
            app = SeshiApp(conn=tmp_db)
            async with app.run_test() as pilot:
                search = app.query_one(SearchBar)
                assert search.sort_mode == "frecency"
                await pilot.press("s")
                assert app._sessions_list.sort_mode == "recency"
                await pilot.press("s")
                assert app._sessions_list.sort_mode == "frequency"
                await pilot.press("s")
                assert app._sessions_list.sort_mode == "frecency"

        asyncio.run(run_case())
