import time

from seshi.prompt_text import extract_command_text, replace_command_tags, strip_markup_tags, strip_system_blocks
from seshi.tui.sessions import SessionsList


def _insert_session(conn, session_id, first_prompt):
    ts = int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, first_prompt, created_at, last_activity_at)
        VALUES (?,?,?,?,?,?)""",
        (session_id, "/home/user/project", "[]", first_prompt, ts, ts),
    )
    conn.commit()
    from seshi.session_index import index_session_search
    index_session_search(conn, session_id)
    conn.commit()


def test_strip_markup_tags_removes_xml_style_tags():
    text = "<local-command-caveat>Caveat</local-command-caveat> Open the repo"

    assert strip_markup_tags(text) == "Caveat Open the repo"


def test_strip_markup_tags_handles_self_closing_tags():
    assert strip_markup_tags("<br/>Open the repo") == "Open the repo"


def test_strip_markup_tags_keeps_non_tag_angle_brackets():
    assert strip_markup_tags("compare 2 < 3 > 1") == "compare 2 < 3 > 1"


def test_strip_system_blocks_removes_caveat_content():
    text = "<local-command-caveat>Caveat: system message</local-command-caveat> Open the repo"
    assert strip_system_blocks(text) == "Open the repo"


def test_strip_system_blocks_removes_multiple_blocks():
    text = "<command-name>/clear</command-name><command-message>clear</command-message> actual prompt"
    assert strip_system_blocks(text) == "actual prompt"


def test_strip_system_blocks_preserves_non_system_tags():
    text = "<custom-tag>keep this</custom-tag> and this"
    assert strip_system_blocks(text) == "<custom-tag>keep this</custom-tag> and this"


def test_sessions_list_render_strips_system_blocks_from_prompt(tmp_db):
    _insert_session(
        tmp_db,
        "tagged-prompt",
        "<local-command-caveat>Caveat</local-command-caveat> Open the repo",
    )

    rendered = SessionsList(tmp_db).render().plain

    assert "Caveat" not in rendered
    assert "Open the repo" in rendered


def test_sessions_list_hides_system_block_only_prompts(tmp_db):
    _insert_session(tmp_db, "s1", "real prompt")
    tmp_db.execute(
        "INSERT INTO prompts (session_id, prompt_index, text) VALUES (?, ?, ?)",
        ("s1", 0, "real prompt"),
    )
    tmp_db.execute(
        "INSERT INTO prompts (session_id, prompt_index, text) VALUES (?, ?, ?)",
        ("s1", 1, "<command-name>/clear</command-name><command-message>clear</command-message><command-args></command-args>"),
    )
    tmp_db.execute(
        "INSERT INTO prompts (session_id, prompt_index, text) VALUES (?, ?, ?)",
        ("s1", 2, "second real prompt"),
    )
    tmp_db.commit()

    sl = SessionsList(tmp_db)
    # Sessions start collapsed by default; expand to see prompts
    sl._collapsed.discard("s1")
    sl._build_display_rows()
    rendered = sl.render().plain
    lines = [l for l in rendered.split("\n") if l.strip()]

    prompt_lines = [l for l in lines if "│" in l]
    assert len(prompt_lines) == 3
    assert any("real prompt" in l for l in prompt_lines)
    assert any("/clear" in l for l in prompt_lines)
    assert any("second real prompt" in l for l in prompt_lines)


def test_extract_command_text_basic():
    text = "<command-name>/fullsend-autopilot</command-name><command-message>fullsend-autopilot</command-message><command-args>fix the login bug</command-args>"
    assert extract_command_text(text) == "/fullsend-autopilot fix the login bug"


def test_extract_command_text_no_args():
    text = "<command-name>/clear</command-name><command-message>clear</command-message>"
    assert extract_command_text(text) == "/clear"


def test_extract_command_text_empty_args():
    text = "<command-name>/clear</command-name><command-message>clear</command-message><command-args></command-args>"
    assert extract_command_text(text) == "/clear"


def test_extract_command_text_no_commands():
    text = "plain text with no command tags"
    assert extract_command_text(text) is None


def test_replace_command_tags_produces_readable_text():
    text = "<command-name>/foo</command-name><command-message>foo</command-message><command-args>bar baz</command-args>"
    result = replace_command_tags(text)
    # After replacing command tags, strip_system_blocks should preserve the text
    cleaned = strip_system_blocks(result)
    assert cleaned == "/foo bar baz"


def test_replace_command_tags_mixed_content():
    text = "<command-name>/clear</command-name><command-message>clear</command-message> actual prompt"
    result = replace_command_tags(text)
    cleaned = strip_system_blocks(result)
    assert "actual prompt" in cleaned
    assert "/clear" in cleaned


def test_replace_command_tags_no_commands():
    text = "plain text without commands"
    assert replace_command_tags(text) == text


def test_toggle_expand_no_prompts(tmp_db):
    _insert_session(tmp_db, "no-prompts", "some prompt")
    sl = SessionsList(tmp_db)
    # Session has no prompts in the prompts table
    old_collapsed = sl._collapsed.copy()
    sl._toggle_expand()
    # Should be a no-op since no prompts are loaded
    assert sl._collapsed == old_collapsed


def test_sessions_list_search_finds_visible_prompt_text(tmp_db):
    _insert_session(
        tmp_db,
        "tagged-prompt",
        "<local-command-caveat>Caveat</local-command-caveat> Open the repo",
    )

    view = SessionsList(tmp_db)
    view.filter("Open")

    assert [s.session_id for s in view.sessions] == ["tagged-prompt"]
