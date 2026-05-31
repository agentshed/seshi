"""Tests for ai_title extraction and display throughout the pipeline.

Claude Code writes session names as:
  - ai-title events (auto-generated titles)
  - custom-title events (user /rename)

Seshi extracts these into the ai_title column and uses the fallback chain:
  custom_name → ai_title → first_prompt → "(untitled)"
"""
import json
import time

from seshi.drain import drain_queue
from seshi.models import Session
from seshi.scan import fix_prompts, scan_projects
from seshi.search import session_resolve, rank_sessions
from seshi.session_index import index_session_search
from seshi.transcript import parse_transcript


def _write_jsonl(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SID2 = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"


def _insert_session(conn, session_id, cwd="/home", custom_name=None,
                    ai_title=None, first_prompt=None, is_favorite=0, ts=None):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, custom_name, ai_title, first_prompt,
         is_favorite, created_at, last_activity_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (session_id, cwd, "[]", custom_name, ai_title, first_prompt, is_favorite, ts, ts),
    )
    conn.commit()


# ── parse_transcript: ai-title extraction ──


class TestParseTranscriptAiTitle:

    def test_extracts_ai_title(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "Fix auth bug", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "fix the auth"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "Fix auth bug"

    def test_extracts_last_ai_title(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "First title", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
            {"type": "ai-title", "aiTitle": "Updated title", "sessionId": "x"},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "Updated title"

    def test_no_ai_title_returns_none(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title is None

    def test_empty_ai_title_ignored(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title is None

    def test_ai_title_missing_field_ignored(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title is None

    def test_ai_title_not_counted_as_message(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "My title", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.message_count == 1

    def test_ai_title_does_not_affect_first_prompt(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "My title", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "the real prompt"}},
        ])
        s = parse_transcript(f)
        assert s.first_prompt == "the real prompt"
        assert s.ai_title == "My title"


# ── parse_transcript: custom-title extraction ──


class TestParseTranscriptCustomTitle:

    def test_extracts_custom_title(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "custom-title", "customTitle": "my-name", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "my-name"

    def test_custom_title_overrides_ai_title(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "Auto generated", "sessionId": "x"},
            {"type": "custom-title", "customTitle": "User chosen", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "User chosen"

    def test_custom_title_overrides_even_when_ai_title_comes_after(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "custom-title", "customTitle": "User chosen", "sessionId": "x"},
            {"type": "ai-title", "aiTitle": "Auto generated later", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "User chosen"

    def test_last_custom_title_wins(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "custom-title", "customTitle": "first rename", "sessionId": "x"},
            {"type": "custom-title", "customTitle": "second rename", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "second rename"

    def test_custom_title_strips_surrounding_quotes(self, tmp_path):
        """Claude Code wraps /rename values in escaped quotes."""
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "custom-title", "customTitle": '"Image"', "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "Image"

    def test_custom_title_with_inner_quotes_preserved(self, tmp_path):
        """Title with quotes in the middle are preserved."""
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "custom-title", "customTitle": 'say "hello" world', "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == 'say "hello" world'

    def test_empty_custom_title_ignored(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "Auto title", "sessionId": "x"},
            {"type": "custom-title", "customTitle": "", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "Auto title"

    def test_custom_title_quotes_only_becomes_empty_and_ignored(self, tmp_path):
        """A customTitle of just '""' should strip to empty and be ignored."""
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "Fallback", "sessionId": "x"},
            {"type": "custom-title", "customTitle": '""', "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "Fallback"

    def test_custom_title_missing_field_ignored(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "custom-title", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title is None


# ── scan_projects: ai_title population ──


class TestScanAiTitle:

    def test_scan_stores_ai_title(self, tmp_db, tmp_path):
        project = tmp_path / "-home"
        project.mkdir()
        _write_jsonl(project / f"{SID}.jsonl", [
            {"type": "ai-title", "aiTitle": "My Session", "sessionId": SID},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        scan_projects(tmp_db, projects_root=tmp_path)
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        assert row["ai_title"] == "My Session"

    def test_scan_stores_custom_title(self, tmp_db, tmp_path):
        project = tmp_path / "-home"
        project.mkdir()
        _write_jsonl(project / f"{SID}.jsonl", [
            {"type": "ai-title", "aiTitle": "Auto name", "sessionId": SID},
            {"type": "custom-title", "customTitle": "User name", "sessionId": SID},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        scan_projects(tmp_db, projects_root=tmp_path)
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        assert row["ai_title"] == "User name"

    def test_scan_no_title_leaves_null(self, tmp_db, tmp_path):
        project = tmp_path / "-home"
        project.mkdir()
        _write_jsonl(project / f"{SID}.jsonl", [
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        scan_projects(tmp_db, projects_root=tmp_path)
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        assert row["ai_title"] is None

    def test_rescan_updates_ai_title(self, tmp_db, tmp_path):
        """When a session already exists, rescan should update ai_title."""
        project = tmp_path / "-home"
        project.mkdir()
        jsonl = project / f"{SID}.jsonl"

        _write_jsonl(jsonl, [
            {"type": "ai-title", "aiTitle": "Original", "sessionId": SID},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        scan_projects(tmp_db, projects_root=tmp_path)

        _write_jsonl(jsonl, [
            {"type": "ai-title", "aiTitle": "Original", "sessionId": SID},
            {"type": "custom-title", "customTitle": "Renamed", "sessionId": SID},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        scan_projects(tmp_db, projects_root=tmp_path)

        row = tmp_db.execute(
            "SELECT ai_title FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        assert row["ai_title"] == "Renamed"


# ── fix_prompts: ai_title update ──


class TestFixPromptsAiTitle:

    def test_fix_prompts_populates_ai_title(self, tmp_db, tmp_path, monkeypatch):
        transcript = tmp_path / f"{SID}.jsonl"
        _write_jsonl(transcript, [
            {"type": "ai-title", "aiTitle": "My Session", "sessionId": SID},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        _insert_session(tmp_db, SID, first_prompt="hello")
        monkeypatch.setattr(
            "seshi.scan.find_transcript_path",
            lambda s: transcript if s == SID else None,
        )
        count = fix_prompts(tmp_db)
        assert count == 1
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        assert row["ai_title"] == "My Session"

    def test_fix_prompts_updates_changed_ai_title(self, tmp_db, tmp_path, monkeypatch):
        transcript = tmp_path / f"{SID}.jsonl"
        _write_jsonl(transcript, [
            {"type": "custom-title", "customTitle": "New Name", "sessionId": SID},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        _insert_session(tmp_db, SID, ai_title="Old Name", first_prompt="hello")
        monkeypatch.setattr(
            "seshi.scan.find_transcript_path",
            lambda s: transcript if s == SID else None,
        )
        count = fix_prompts(tmp_db)
        assert count == 1
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        assert row["ai_title"] == "New Name"

    def test_fix_prompts_no_change_when_matching(self, tmp_db, tmp_path, monkeypatch):
        transcript = tmp_path / f"{SID}.jsonl"
        _write_jsonl(transcript, [
            {"type": "ai-title", "aiTitle": "Same", "sessionId": SID},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        _insert_session(tmp_db, SID, ai_title="Same", first_prompt="hello")
        monkeypatch.setattr(
            "seshi.scan.find_transcript_path",
            lambda s: transcript if s == SID else None,
        )
        count = fix_prompts(tmp_db)
        assert count == 0

    def test_fix_prompts_no_transcript_skips(self, tmp_db, monkeypatch):
        _insert_session(tmp_db, SID, first_prompt="hello")
        monkeypatch.setattr(
            "seshi.scan.find_transcript_path",
            lambda _s: None,
        )
        count = fix_prompts(tmp_db)
        assert count == 0


# ── session_resolve: ai_title lookup ──


class TestSessionResolveAiTitle:

    def test_resolve_by_ai_title(self, tmp_db):
        _insert_session(tmp_db, SID, ai_title="my-session")
        result = session_resolve(tmp_db, "my-session")
        assert result is not None
        assert result.session_id == SID

    def test_resolve_ai_title_case_insensitive(self, tmp_db):
        _insert_session(tmp_db, SID, ai_title="My Session")
        result = session_resolve(tmp_db, "my session")
        assert result is not None
        assert result.session_id == SID

    def test_custom_name_takes_priority_over_ai_title(self, tmp_db):
        _insert_session(tmp_db, SID, custom_name="seshi-name", ai_title="claude-name")
        _insert_session(tmp_db, SID2, custom_name="claude-name")
        result = session_resolve(tmp_db, "claude-name")
        assert result is not None
        assert result.session_id == SID2

    def test_ai_title_before_session_id_lookup(self, tmp_db):
        _insert_session(tmp_db, SID, ai_title="some-title")
        result = session_resolve(tmp_db, "some-title")
        assert result is not None
        assert result.session_id == SID

    def test_resolve_falls_through_to_session_id(self, tmp_db):
        _insert_session(tmp_db, SID)
        result = session_resolve(tmp_db, SID)
        assert result is not None

    def test_resolve_not_found_with_no_matches(self, tmp_db):
        _insert_session(tmp_db, SID, ai_title="something")
        result = session_resolve(tmp_db, "nonexistent")
        assert result is None

    def test_resolve_ai_title_returns_most_recent(self, tmp_db):
        """When multiple sessions share an ai_title, return the most recent."""
        now = int(time.time())
        _insert_session(tmp_db, SID, ai_title="shared-name", ts=now - 3600)
        _insert_session(tmp_db, SID2, ai_title="shared-name", ts=now)
        result = session_resolve(tmp_db, "shared-name")
        assert result is not None
        assert result.session_id == SID2


# ── Session model: ai_title field ──


class TestSessionModel:

    def test_from_row_includes_ai_title(self, tmp_db):
        _insert_session(tmp_db, SID, ai_title="test-title")
        row = tmp_db.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        session = Session.from_row(row)
        assert session.ai_title == "test-title"

    def test_from_row_ai_title_none(self, tmp_db):
        _insert_session(tmp_db, SID)
        row = tmp_db.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        session = Session.from_row(row)
        assert session.ai_title is None


# ── Display fallback chain ──


class TestDisplayFallback:
    """Verify custom_name → ai_title → first_prompt → "(untitled)" chain."""

    def _display_name(self, session):
        """Reproduce the fallback logic used in sessions.py line 336."""
        return (session.custom_name or session.ai_title
                or session.first_prompt or "(untitled)")

    def test_custom_name_wins(self, tmp_db):
        _insert_session(tmp_db, SID, custom_name="seshi-name",
                        ai_title="claude-name", first_prompt="the prompt")
        row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = ?", (SID,)).fetchone()
        s = Session.from_row(row)
        assert self._display_name(s) == "seshi-name"

    def test_ai_title_over_first_prompt(self, tmp_db):
        _insert_session(tmp_db, SID, ai_title="claude-name", first_prompt="the prompt")
        row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = ?", (SID,)).fetchone()
        s = Session.from_row(row)
        assert self._display_name(s) == "claude-name"

    def test_first_prompt_when_no_names(self, tmp_db):
        _insert_session(tmp_db, SID, first_prompt="the prompt")
        row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = ?", (SID,)).fetchone()
        s = Session.from_row(row)
        assert self._display_name(s) == "the prompt"

    def test_untitled_when_nothing_set(self, tmp_db):
        _insert_session(tmp_db, SID)
        row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = ?", (SID,)).fetchone()
        s = Session.from_row(row)
        assert self._display_name(s) == "(untitled)"

    def test_empty_custom_name_falls_to_ai_title(self, tmp_db):
        """custom_name=None should fall through to ai_title."""
        _insert_session(tmp_db, SID, custom_name=None, ai_title="title")
        row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = ?", (SID,)).fetchone()
        s = Session.from_row(row)
        assert self._display_name(s) == "title"


# ── Search indexing: ai_title in FTS ──


class TestSearchIndexAiTitle:

    def test_ai_title_indexed_for_search(self, tmp_db):
        _insert_session(tmp_db, SID, ai_title="kubernetes deploy")
        index_session_search(tmp_db, SID)
        tmp_db.commit()
        results = rank_sessions(tmp_db, "kubernetes")
        ids = [s.session_id for s, _ in results]
        assert SID in ids

    def test_custom_name_preferred_in_index(self, tmp_db):
        _insert_session(tmp_db, SID, custom_name="my-deploy",
                        ai_title="kubernetes deploy")
        index_session_search(tmp_db, SID)
        tmp_db.commit()
        results = rank_sessions(tmp_db, "my-deploy")
        ids = [s.session_id for s, _ in results]
        assert SID in ids

    def test_no_title_still_indexes(self, tmp_db):
        _insert_session(tmp_db, SID, first_prompt="fix the auth bug")
        index_session_search(tmp_db, SID)
        tmp_db.commit()
        results = rank_sessions(tmp_db, "auth")
        ids = [s.session_id for s, _ in results]
        assert SID in ids

    def test_ai_title_name_outranks_prompt_match(self, tmp_db):
        """Session with ai_title containing the term should rank above
        a session that only mentions it in the first_prompt."""
        _insert_session(tmp_db, SID, ai_title="auth rewrite")
        _insert_session(tmp_db, SID2, first_prompt="fix the auth layer")
        index_session_search(tmp_db, SID)
        index_session_search(tmp_db, SID2)
        tmp_db.commit()
        results = rank_sessions(tmp_db, "auth")
        ids = [s.session_id for s, _ in results]
        assert ids.index(SID) < ids.index(SID2)


# ── DB schema: ai_title column ──


class TestDbSchemaAiTitle:

    def test_column_exists(self, tmp_db):
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions LIMIT 0"
        ).fetchone()
        # No error means column exists
        assert row is None

    def test_column_nullable(self, tmp_db):
        _insert_session(tmp_db, SID)
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        assert row["ai_title"] is None

    def test_column_stores_value(self, tmp_db):
        _insert_session(tmp_db, SID, ai_title="test")
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        assert row["ai_title"] == "test"

    def test_migration_idempotent(self, tmp_db):
        """Re-running init_schema shouldn't error on existing ai_title column."""
        from seshi.db import init_schema
        init_schema(tmp_db)
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions LIMIT 0"
        ).fetchone()
        assert row is None


# ── Edge cases: mixed events and malformed data ──


class TestEdgeCases:

    def test_agent_name_event_ignored(self, tmp_path):
        """agent-name events should not affect ai_title."""
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "agent-name", "agentName": "agent label", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title is None

    def test_interleaved_title_events(self, tmp_path):
        """Multiple ai-title and custom-title events interleaved."""
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "Auto 1", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
            {"type": "custom-title", "customTitle": "User 1", "sessionId": "x"},
            {"type": "ai-title", "aiTitle": "Auto 2", "sessionId": "x"},
            {"type": "custom-title", "customTitle": "User 2", "sessionId": "x"},
            {"type": "ai-title", "aiTitle": "Auto 3", "sessionId": "x"},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "User 2"

    def test_only_ai_title_no_messages(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": "Title Only", "sessionId": "x"},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "Title Only"
        assert s.first_prompt is None
        assert s.message_count == 0

    def test_malformed_title_event_skipped(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title"},
            {"type": "custom-title"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title is None

    def test_unicode_title(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "custom-title", "customTitle": "修正バグ 🐛", "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == "修正バグ 🐛"

    def test_very_long_title(self, tmp_path):
        long_title = "a" * 1000
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": long_title, "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == long_title

    def test_title_with_special_characters(self, tmp_path):
        f = tmp_path / "test.jsonl"
        _write_jsonl(f, [
            {"type": "ai-title", "aiTitle": 'Fix "auth" & <deploy>', "sessionId": "x"},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        s = parse_transcript(f)
        assert s.ai_title == 'Fix "auth" & <deploy>'

    def test_drain_preserves_ai_title_on_start(self, tmp_db, tmp_path):
        """Drain's INSERT OR IGNORE shouldn't overwrite ai_title set by scan."""
        from unittest import mock
        _insert_session(tmp_db, "abc-123", ai_title="from scan")
        q = tmp_path / "queue.jsonl"
        q.write_text(json.dumps({
            "event": "start", "ts": 1000, "session_id": "abc-123",
            "cwd": "/home", "argv": "claude",
        }) + "\n")
        with mock.patch("seshi.drain.QUEUE_PATH", q):
            drain_queue(tmp_db)
        row = tmp_db.execute(
            "SELECT ai_title FROM sessions WHERE session_id = 'abc-123'"
        ).fetchone()
        assert row["ai_title"] == "from scan"

    def test_scan_does_not_overwrite_seshi_custom_name(self, tmp_db, tmp_path):
        """Scanning a transcript with ai_title shouldn't touch custom_name."""
        project = tmp_path / "-home"
        project.mkdir()
        _write_jsonl(project / f"{SID}.jsonl", [
            {"type": "ai-title", "aiTitle": "Auto name", "sessionId": SID},
            {"timestamp": "2025-01-01T00:00:00Z",
             "message": {"role": "user", "content": "hello"}},
        ])
        scan_projects(tmp_db, projects_root=tmp_path)
        tmp_db.execute(
            "UPDATE sessions SET custom_name = 'user-renamed' WHERE session_id = ?",
            (SID,),
        )
        tmp_db.commit()

        scan_projects(tmp_db, projects_root=tmp_path)
        row = tmp_db.execute(
            "SELECT custom_name, ai_title FROM sessions WHERE session_id = ?", (SID,)
        ).fetchone()
        assert row["custom_name"] == "user-renamed"
        assert row["ai_title"] == "Auto name"
