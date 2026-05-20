import json
from pathlib import Path
from seshi.transcript import parse_transcript, extract_messages


def _write_jsonl(path: Path, messages):
    path.write_text("\n".join(json.dumps(m) for m in messages) + "\n")


def test_parse_text_content(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z", "message": {"role": "user", "content": "hello world"}},
    ])
    s = parse_transcript(f)
    assert s.first_prompt == "hello world"
    assert s.message_count == 1


def test_parse_array_content(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z", "message": {"role": "user", "content": [{"type": "text", "text": "block text"}]}},
    ])
    s = parse_transcript(f)
    assert s.first_prompt == "block text"


def test_token_counting(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z", "message": {"role": "user", "content": "hi", "usage": {"input_tokens": 100, "output_tokens": 0}}},
        {"timestamp": "2025-01-01T00:01:00Z", "message": {"role": "assistant", "content": "hello", "usage": {"input_tokens": 0, "output_tokens": 200}}},
    ])
    s = parse_transcript(f)
    assert s.token_count == 300


def test_timestamp_extraction(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z", "message": {"role": "user", "content": "hi"}},
        {"timestamp": "2025-01-01T01:00:00Z", "message": {"role": "assistant", "content": "hello"}},
    ])
    s = parse_transcript(f)
    assert s.first_ts is not None
    assert s.last_ts is not None
    assert s.last_ts > s.first_ts


def test_extract_messages_limit(tmp_path):
    f = tmp_path / "test.jsonl"
    msgs = [{"timestamp": f"2025-01-01T00:0{i}:00Z", "message": {"role": "user", "content": f"msg {i}"}} for i in range(5)]
    _write_jsonl(f, msgs)
    result = extract_messages(f, limit=3)
    assert len(result) == 3


def test_nonexistent_file():
    s = parse_transcript(Path("/nonexistent/file.jsonl"))
    assert s.message_count == 0
    assert s.first_prompt is None
