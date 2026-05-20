import json
from pathlib import Path
from seshi.scan import scan_projects


def _make_transcript(path: Path, messages=None):
    messages = messages or [
        {"timestamp": "2025-01-01T00:00:00Z", "message": {"role": "user", "content": "hello", "usage": {"input_tokens": 10, "output_tokens": 0}}},
        {"timestamp": "2025-01-01T00:01:00Z", "message": {"role": "assistant", "content": "hi", "usage": {"input_tokens": 0, "output_tokens": 20}}},
    ]
    path.write_text("\n".join(json.dumps(m) for m in messages) + "\n")


def test_pattern_a_jsonl(tmp_db, tmp_path):
    project = tmp_path / "-home"
    project.mkdir()
    _make_transcript(project / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl")
    count = scan_projects(tmp_db, projects_root=tmp_path)
    assert count == 1
    row = tmp_db.execute("SELECT * FROM sessions WHERE session_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'").fetchone()
    assert row is not None
    assert row["is_backfilled"] == 1


def test_pattern_b_directory(tmp_db, tmp_path):
    project = tmp_path / "-home"
    project.mkdir()
    session_dir = project / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    session_dir.mkdir()
    count = scan_projects(tmp_db, projects_root=tmp_path)
    assert count == 1


def test_idempotent(tmp_db, tmp_path):
    project = tmp_path / "-home"
    project.mkdir()
    _make_transcript(project / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl")
    scan_projects(tmp_db, projects_root=tmp_path)
    count = scan_projects(tmp_db, projects_root=tmp_path)
    assert count == 0


def test_skip_skill_injections(tmp_db, tmp_path):
    project = tmp_path / "-home"
    project.mkdir()
    _make_transcript(project / "skill-injections.jsonl")
    count = scan_projects(tmp_db, projects_root=tmp_path)
    assert count == 0


def test_no_double_insert(tmp_db, tmp_path):
    project = tmp_path / "-home"
    project.mkdir()
    _make_transcript(project / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl")
    (project / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee").mkdir()
    count = scan_projects(tmp_db, projects_root=tmp_path)
    assert count == 1


def test_missing_root(tmp_db, tmp_path):
    count = scan_projects(tmp_db, projects_root=tmp_path / "nonexistent")
    assert count == 0
