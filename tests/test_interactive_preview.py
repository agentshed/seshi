"""Tests for interactive preview pane: Tab-to-focus with scrollable transcript."""
from unittest.mock import MagicMock, PropertyMock, patch
from textual.geometry import Size

from seshi.tui.preview import Preview
from seshi.tui.footer import Footer
from seshi.models import Session


def _make_session(session_id="s1", msg_count=20):
    return Session(
        session_id=session_id,
        cwd="/tmp/project",
        launch_argv_json="[]",
        env_json=None,
        git_branch=None,
        git_sha=None,
        first_prompt="Hello",
        custom_name=None,
        ai_title=None,
        is_favorite=0,
        is_archived=0,
        is_backfilled=0,
        message_count=msg_count,
        token_count=500,
        status="completed",
        created_at=1000000,
        last_activity_at=1000000,
        origin_host=None,
        schema_version=1,
    )


def _make_messages(count=20):
    messages = []
    for i in range(count):
        msg = MagicMock()
        msg.role = "user" if i % 2 == 0 else "assistant"
        msg.text = f"Message {i}" + " extra words" * 5
        messages.append(msg)
    return messages


def _render_with_size(preview, width=120, height=20):
    with patch.object(type(preview), "size", new_callable=PropertyMock,
                      return_value=Size(width, height)):
        return preview.render()


class TestPreviewCanFocus:
    def test_preview_has_can_focus(self):
        p = Preview()
        assert p.can_focus is True


class TestPreviewScrolling:
    def _setup_preview(self, msg_count=50, height=20):
        p = Preview()
        session = _make_session(msg_count=msg_count)
        messages = _make_messages(msg_count)

        with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
             patch("seshi.tui.preview.extract_messages", return_value=messages):
            p.session = session

        return p, messages

    def test_scroll_offset_starts_at_zero(self):
        p, _ = self._setup_preview()
        assert p._scroll_offset == 0

    def test_scroll_down_with_j(self):
        p, messages = self._setup_preview(50)

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True), \
             patch.object(type(p), "size", new_callable=PropertyMock, return_value=Size(120, 20)):
            from textual.events import Key
            event = MagicMock(spec=Key)
            event.key = "j"
            event.prevent_default = MagicMock()
            event.stop = MagicMock()
            p.on_key(event)
            assert p._scroll_offset == 1
            event.prevent_default.assert_called_once()
            event.stop.assert_called_once()

    def test_scroll_up_with_k(self):
        p, _ = self._setup_preview(50)
        p._scroll_offset = 5

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True), \
             patch.object(type(p), "size", new_callable=PropertyMock, return_value=Size(120, 20)):
            event = MagicMock()
            event.key = "k"
            event.prevent_default = MagicMock()
            event.stop = MagicMock()
            p.on_key(event)
            assert p._scroll_offset == 4

    def test_scroll_k_does_not_go_below_zero(self):
        p, _ = self._setup_preview(50)
        p._scroll_offset = 0

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True), \
             patch.object(type(p), "size", new_callable=PropertyMock, return_value=Size(120, 20)):
            event = MagicMock()
            event.key = "k"
            event.prevent_default = MagicMock()
            event.stop = MagicMock()
            p.on_key(event)
            assert p._scroll_offset == 0

    def test_jump_to_top_with_g(self):
        p, _ = self._setup_preview(50)
        p._scroll_offset = 30

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True), \
             patch.object(type(p), "size", new_callable=PropertyMock, return_value=Size(120, 20)):
            event = MagicMock()
            event.key = "g"
            event.prevent_default = MagicMock()
            event.stop = MagicMock()
            p.on_key(event)
            assert p._scroll_offset == 0

    def test_jump_to_bottom_with_G(self):
        p, messages = self._setup_preview(50, 20)

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True), \
             patch.object(type(p), "size", new_callable=PropertyMock, return_value=Size(120, 20)):
            event = MagicMock()
            event.key = "G"
            event.prevent_default = MagicMock()
            event.stop = MagicMock()
            p.on_key(event)
            # available_lines = max(20 - 2, 4) = 18
            # max_offset = max(0, 50 - 18) = 32
            assert p._scroll_offset == 32

    def test_page_down_with_ctrl_d(self):
        p, _ = self._setup_preview(50)

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True), \
             patch.object(type(p), "size", new_callable=PropertyMock, return_value=Size(120, 20)):
            event = MagicMock()
            event.key = "ctrl+d"
            event.prevent_default = MagicMock()
            event.stop = MagicMock()
            p.on_key(event)
            # page = max(1, 18 // 2) = 9
            assert p._scroll_offset == 9

    def test_page_up_with_ctrl_u(self):
        p, _ = self._setup_preview(50)
        p._scroll_offset = 20

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True), \
             patch.object(type(p), "size", new_callable=PropertyMock, return_value=Size(120, 20)):
            event = MagicMock()
            event.key = "ctrl+u"
            event.prevent_default = MagicMock()
            event.stop = MagicMock()
            p.on_key(event)
            # page = 9, so 20 - 9 = 11
            assert p._scroll_offset == 11

    def test_unhandled_key_not_stopped(self):
        p, _ = self._setup_preview(50)

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True), \
             patch.object(type(p), "size", new_callable=PropertyMock, return_value=Size(120, 20)):
            event = MagicMock()
            event.key = "x"
            event.prevent_default = MagicMock()
            event.stop = MagicMock()
            p.on_key(event)
            event.prevent_default.assert_not_called()
            event.stop.assert_not_called()

    def test_no_scroll_when_not_focused(self):
        p, _ = self._setup_preview(50)

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=False):
            event = MagicMock()
            event.key = "j"
            event.prevent_default = MagicMock()
            event.stop = MagicMock()
            p.on_key(event)
            assert p._scroll_offset == 0
            event.prevent_default.assert_not_called()


class TestPreviewScrollIndicator:
    def test_scroll_indicator_shown_when_focused(self):
        p = Preview()
        session = _make_session(msg_count=50)
        messages = _make_messages(50)

        with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
             patch("seshi.tui.preview.extract_messages", return_value=messages):
            p.session = session

        p._scroll_offset = 0

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True):
            rendered = _render_with_size(p)

        # Should contain scroll position like [1-18/50]
        assert "[1-18/50]" in rendered.plain

    def test_scroll_indicator_not_shown_when_unfocused(self):
        p = Preview()
        session = _make_session(msg_count=50)
        messages = _make_messages(50)

        with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
             patch("seshi.tui.preview.extract_messages", return_value=messages):
            p.session = session

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=False):
            rendered = _render_with_size(p)

        # Should show message/token stats instead
        assert "msgs" in rendered.plain
        assert "tok" in rendered.plain

    def test_scroll_indicator_updates_with_offset(self):
        p = Preview()
        session = _make_session(msg_count=50)
        messages = _make_messages(50)

        with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
             patch("seshi.tui.preview.extract_messages", return_value=messages):
            p.session = session

        p._scroll_offset = 10

        with patch.object(type(p), "has_focus", new_callable=PropertyMock, return_value=True):
            rendered = _render_with_size(p)

        assert "[11-28/50]" in rendered.plain


class TestPreviewBlurReset:
    def test_blur_resets_scroll_offset(self):
        p = Preview()
        p._scroll_offset = 15

        from textual.events import Blur
        blur_event = MagicMock(spec=Blur)
        p.on_blur(blur_event)

        assert p._scroll_offset == 0


class TestPreviewMessageCache:
    def test_cache_populated_on_session_set(self):
        p = Preview()
        session = _make_session()
        messages = _make_messages(5)

        with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
             patch("seshi.tui.preview.extract_messages", return_value=messages):
            p.session = session

        assert p._cached_session_id == "s1"
        assert len(p._cached_messages) == 5

    def test_cache_reused_for_same_session(self):
        p = Preview()
        session = _make_session()
        messages = _make_messages(5)

        with patch("seshi.tui.preview.find_transcript_path", return_value="/fake") as mock_find, \
             patch("seshi.tui.preview.extract_messages", return_value=messages) as mock_extract:
            p.session = session
            # Update again with same session
            p._update_cache(session)

        # extract_messages should only be called once (cache hit)
        assert mock_extract.call_count == 1

    def test_cache_refreshed_for_different_session(self):
        p = Preview()
        messages1 = _make_messages(5)
        messages2 = _make_messages(10)

        with patch("seshi.tui.preview.find_transcript_path", return_value="/fake"), \
             patch("seshi.tui.preview.extract_messages", side_effect=[messages1, messages2]):
            p.session = _make_session("s1")
            assert len(p._cached_messages) == 5
            p.session = _make_session("s2")
            assert len(p._cached_messages) == 10


class TestFooterPreviewFocused:
    def test_footer_shows_scroll_hints_when_preview_focused(self):
        f = Footer()
        f.preview_focused = True
        f.view = "sessions"
        rendered = f.render()
        plain = rendered.plain
        assert "scroll" in plain
        assert "back" in plain

    def test_footer_shows_normal_hints_when_preview_not_focused(self):
        f = Footer()
        f.preview_focused = False
        f.view = "sessions"
        rendered = f.render()
        plain = rendered.plain
        assert "resume" in plain

    def test_footer_preview_focused_reactive_default(self):
        f = Footer()
        assert f.preview_focused is False
