"""Tests for theme-aware preview pane colors."""
from unittest.mock import MagicMock, PropertyMock, patch
from seshi.tui.preview import Preview
from seshi.models import Session


def _make_session(session_id="s1"):
    return Session(
        session_id=session_id,
        cwd="/tmp/project",
        launch_argv_json="[]",
        env_json=None,
        git_branch=None,
        git_sha=None,
        first_prompt="What is this?",
        custom_name=None,
        is_favorite=0,
        is_archived=0,
        is_backfilled=0,
        message_count=4,
        token_count=100,
        status="completed",
        created_at=1000000,
        last_activity_at=1000000,
        origin_host=None,
        schema_version=1,
    )


def _make_preview_with_size(**kwargs):
    p = Preview(**kwargs)
    mock_size = MagicMock()
    mock_size.width = 120
    mock_size.height = 20
    type(p).size = PropertyMock(return_value=mock_size)
    return p


def _mock_messages():
    msg_user = MagicMock()
    msg_user.role = "user"
    msg_user.text = "What is this?"
    msg_asst = MagicMock()
    msg_asst.role = "assistant"
    msg_asst.text = "This is a test."
    return [msg_user, msg_asst]


def test_preview_uses_custom_user_color():
    p = _make_preview_with_size()
    p.user_color = "#FF0000"
    p.session = _make_session()

    with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
         patch("seshi.tui.preview.extract_messages", return_value=_mock_messages()):
        rendered = p.render()

    spans = rendered._spans
    has_color = any("FF0000" in str(s.style).upper() or "ff0000" in str(s.style) for s in spans)
    assert has_color, f"Expected user color #FF0000 in spans: {[(s.start, s.end, s.style) for s in spans]}"


def test_preview_uses_custom_assistant_color():
    p = _make_preview_with_size()
    p.assistant_color = "#00FF00"
    p.session = _make_session()

    with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
         patch("seshi.tui.preview.extract_messages", return_value=_mock_messages()):
        rendered = p.render()

    spans = rendered._spans
    has_color = any("00FF00" in str(s.style).upper() or "00ff00" in str(s.style) for s in spans)
    assert has_color, f"Expected assistant color #00FF00 in spans"


def test_preview_defaults_to_fallback_colors():
    p = _make_preview_with_size()
    p.session = _make_session()

    with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
         patch("seshi.tui.preview.extract_messages", return_value=_mock_messages()):
        rendered = p.render()

    # Should use the default colors without crashing
    text = rendered.plain
    assert "you" in text
    assert "asst" in text


def test_preview_with_no_session():
    p = _make_preview_with_size()
    p.user_color = "#FF0000"
    p.assistant_color = "#00FF00"
    p.session = None
    rendered = p.render()
    assert "no session selected" in rendered.plain


def test_preview_reacts_to_color_change():
    p = _make_preview_with_size()
    p.user_color = "#FF0000"
    p.session = _make_session()

    with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
         patch("seshi.tui.preview.extract_messages", return_value=_mock_messages()):
        rendered1 = p.render()
        p.user_color = "#0000FF"
        rendered2 = p.render()

    spans1 = rendered1._spans
    spans2 = rendered2._spans
    has_ff0000 = any("FF0000" in str(s.style).upper() for s in spans1)
    has_0000ff = any("0000FF" in str(s.style).upper() for s in spans2)
    assert has_ff0000
    assert has_0000ff
