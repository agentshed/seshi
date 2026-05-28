import time

from seshi.prompt_text import strip_markup_tags, strip_system_blocks
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


def test_sessions_list_search_finds_visible_prompt_text(tmp_db):
    _insert_session(
        tmp_db,
        "tagged-prompt",
        "<local-command-caveat>Caveat</local-command-caveat> Open the repo",
    )

    view = SessionsList(tmp_db)
    view.filter("Open")

    assert [s.session_id for s in view.sessions] == ["tagged-prompt"]
