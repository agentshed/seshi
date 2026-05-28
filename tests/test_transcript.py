import json
from pathlib import Path
from seshi.transcript import parse_transcript, extract_messages, extract_user_prompts


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


def test_parse_skips_is_meta_user_message(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"isMeta": True, "timestamp": "2025-01-01T00:00:00Z",
         "message": {"role": "user", "content": "<local-command-caveat>Caveat: The messages below were generated</local-command-caveat>"}},
        {"timestamp": "2025-01-01T00:00:01Z",
         "message": {"role": "user", "content": "fix the auth bug"}},
    ])
    s = parse_transcript(f)
    assert s.first_prompt == "fix the auth bug"


def test_parse_only_meta_messages(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"isMeta": True, "timestamp": "2025-01-01T00:00:00Z",
         "message": {"role": "user", "content": "<local-command-caveat>Caveat</local-command-caveat>"}},
    ])
    s = parse_transcript(f)
    assert s.first_prompt is None


def test_extract_messages_skips_is_meta(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"isMeta": True, "timestamp": "2025-01-01T00:00:00Z",
         "message": {"role": "user", "content": "system caveat message"}},
        {"timestamp": "2025-01-01T00:00:01Z",
         "message": {"role": "user", "content": "real user message"}},
    ])
    msgs = extract_messages(f)
    assert len(msgs) == 1
    assert msgs[0].text == "real user message"


def test_extract_messages_skips_user_with_only_system_blocks(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z",
         "message": {"role": "user", "content": "<local-command-caveat>Caveat: system only</local-command-caveat>"}},
        {"timestamp": "2025-01-01T00:00:01Z",
         "message": {"role": "assistant", "content": "Here is my response"}},
        {"timestamp": "2025-01-01T00:00:02Z",
         "message": {"role": "user", "content": "real question"}},
    ])
    msgs = extract_messages(f)
    assert len(msgs) == 2
    assert msgs[0].role == "assistant"
    assert msgs[1].role == "user"
    assert msgs[1].text == "real question"


def test_parse_strips_embedded_caveat_from_first_prompt(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z",
         "message": {"role": "user", "content": "<local-command-caveat>Caveat: The messages below were generated</local-command-caveat> fix the auth bug"}},
    ])
    s = parse_transcript(f)
    assert s.first_prompt == "fix the auth bug"


def test_extract_user_prompts_strips_embedded_system_blocks(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z",
         "message": {"role": "user", "content": "<local-command-caveat>Caveat</local-command-caveat><command-name>/clear</command-name> actual question"}},
    ])
    result = extract_user_prompts(f)
    assert len(result) == 1
    assert result[0].text == "actual question"


def test_extract_user_prompts_skips_only_system_blocks(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z",
         "message": {"role": "user", "content": "<local-command-caveat>Caveat: system message only</local-command-caveat>"}},
        {"timestamp": "2025-01-01T00:00:01Z",
         "message": {"role": "user", "content": "real prompt"}},
    ])
    result = extract_user_prompts(f)
    assert len(result) == 1
    assert result[0].text == "real prompt"


def test_extract_user_prompts_basic(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z", "message": {"role": "user", "content": "first question"}},
        {"timestamp": "2025-01-01T00:01:00Z", "message": {"role": "assistant", "content": "first answer"}},
        {"timestamp": "2025-01-01T00:02:00Z", "message": {"role": "user", "content": "second question"}},
        {"timestamp": "2025-01-01T00:03:00Z", "message": {"role": "assistant", "content": "second answer"}},
        {"timestamp": "2025-01-01T00:04:00Z", "message": {"role": "user", "content": "third question"}},
    ])
    result = extract_user_prompts(f)
    assert len(result) == 3
    assert all(m.role == "user" for m in result)
    assert result[0].text == "first question"
    assert result[1].text == "second question"
    assert result[2].text == "third question"


def test_extract_user_prompts_skips_meta(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"isMeta": True, "timestamp": "2025-01-01T00:00:00Z",
         "message": {"role": "user", "content": "<local-command-caveat>Caveat message</local-command-caveat>"}},
        {"timestamp": "2025-01-01T00:00:01Z",
         "message": {"role": "user", "content": "real prompt"}},
        {"isMeta": True, "timestamp": "2025-01-01T00:00:02Z",
         "message": {"role": "user", "content": "another meta message"}},
    ])
    result = extract_user_prompts(f)
    assert len(result) == 1
    assert result[0].text == "real prompt"


def test_extract_user_prompts_empty_file(tmp_path):
    f = tmp_path / "test.jsonl"
    f.write_text("")
    result = extract_user_prompts(f)
    assert result == []


def test_extract_user_prompts_nonexistent_file():
    result = extract_user_prompts(Path("/nonexistent/path/file.jsonl"))
    assert result == []


def test_extract_user_prompts_array_content(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z", "message": {"role": "user", "content": [
            {"type": "text", "text": "hello from"},
            {"type": "text", "text": "array content"},
        ]}},
    ])
    result = extract_user_prompts(f)
    assert len(result) == 1
    assert result[0].text == "hello from array content"


def test_extract_user_prompts_preserves_order(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z", "message": {"role": "user", "content": "alpha"}},
        {"timestamp": "2025-01-01T00:01:00Z", "message": {"role": "assistant", "content": "response"}},
        {"timestamp": "2025-01-01T00:02:00Z", "message": {"role": "user", "content": "beta"}},
        {"timestamp": "2025-01-01T00:03:00Z", "message": {"role": "user", "content": "gamma"}},
    ])
    result = extract_user_prompts(f)
    assert [m.text for m in result] == ["alpha", "beta", "gamma"]


def test_extract_user_prompts_with_timestamps(tmp_path):
    f = tmp_path / "test.jsonl"
    _write_jsonl(f, [
        {"timestamp": "2025-01-01T00:00:00Z", "message": {"role": "user", "content": "first"}},
        {"timestamp": "2025-01-01T00:05:00Z", "message": {"role": "user", "content": "second"}},
    ])
    result = extract_user_prompts(f)
    assert len(result) == 2
    assert result[0].timestamp == "2025-01-01T00:00:00Z"
    assert result[1].timestamp == "2025-01-01T00:05:00Z"
