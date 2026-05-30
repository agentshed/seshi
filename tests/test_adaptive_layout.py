"""Tests for adaptive preview layout (auto-hide at narrow widths, proportional split)."""
import time
from unittest.mock import MagicMock, PropertyMock, patch

from textual.geometry import Size

from seshi.tui.sessions import SessionsList
from seshi.tui.preview import Preview


def _insert_session(conn, session_id, cwd="/tmp/project", custom_name=None,
                    first_prompt=None, is_favorite=0, ts=None):
    ts = ts or int(time.time())
    conn.execute(
        """INSERT INTO sessions
        (session_id, cwd, launch_argv_json, custom_name, first_prompt,
         is_favorite, created_at, last_activity_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (session_id, cwd, "[]", custom_name, first_prompt, is_favorite, ts, ts),
    )
    conn.commit()
    from seshi.session_index import index_session_search
    index_session_search(conn, session_id)
    conn.commit()


def _make_mock_app(width=120, preview_display=True, preview_user_toggled=False):
    mock_preview = MagicMock(spec=Preview)
    mock_preview.display = preview_display
    mock_preview.styles = MagicMock()

    mock_sessions = MagicMock(spec=SessionsList)
    mock_sessions.styles = MagicMock()
    mock_sessions._all_sessions = []

    mock_app = MagicMock()
    mock_app._preview = mock_preview
    mock_app._sessions_list = mock_sessions
    mock_app._preview_user_toggled = preview_user_toggled
    mock_app.current_view = "sessions"

    mock_size = MagicMock()
    mock_size.width = width
    mock_size.height = 40
    type(mock_app).size = PropertyMock(return_value=mock_size)

    return mock_app


def test_preview_auto_hidden_at_narrow_width():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=80)
    SeshiApp._apply_preview_layout(app)
    assert app._preview.display is False


def test_preview_visible_at_wide_width():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=120)
    SeshiApp._apply_preview_layout(app)
    assert app._preview.display is True


def test_preview_boundary_at_100():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=100)
    SeshiApp._apply_preview_layout(app)
    assert app._preview.display is True

    app2 = _make_mock_app(width=99)
    SeshiApp._apply_preview_layout(app2)
    assert app2._preview.display is False


def test_manual_toggle_overrides_auto_hide():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=80, preview_user_toggled=True, preview_display=True)
    SeshiApp._apply_preview_layout(app)
    assert app._preview.display is True


def test_manual_toggle_keeps_hidden_at_wide():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=120, preview_user_toggled=True, preview_display=False)
    SeshiApp._apply_preview_layout(app)
    assert app._preview.display is False


def test_toggle_preview_sets_user_flag():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=120, preview_display=True)
    app._preview_user_toggled = False
    SeshiApp.toggle_preview(app)
    assert app._preview_user_toggled is True
    assert app._preview.display is False


def test_toggle_preview_shows_hidden():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=80, preview_display=False)
    SeshiApp.toggle_preview(app)
    assert app._preview.display is True


def test_on_resize_calls_layout_when_sessions_view():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=80, preview_user_toggled=False)
    app.current_view = "sessions"
    app._apply_preview_layout = MagicMock()
    SeshiApp.on_resize(app, MagicMock())
    app._apply_preview_layout.assert_called_once()


def test_on_resize_skips_when_user_toggled():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=80, preview_user_toggled=True)
    app.current_view = "sessions"
    with patch.object(SeshiApp, '_apply_preview_layout') as mock_apply:
        SeshiApp.on_resize(app, MagicMock())
        mock_apply.assert_not_called()


def test_on_resize_skips_non_sessions_view():
    from seshi.tui.app import SeshiApp
    app = _make_mock_app(width=80, preview_user_toggled=False)
    app.current_view = "overview"
    with patch.object(SeshiApp, '_apply_preview_layout') as mock_apply:
        SeshiApp.on_resize(app, MagicMock())
        mock_apply.assert_not_called()


def test_css_uses_2fr_for_session_list():
    from seshi.tui.styles import theme_css
    from seshi.themes import get_theme
    css = theme_css(get_theme("coral"))
    assert "width: 2fr;" in css or "width: 2fr" in css


def test_css_uses_3fr_for_preview():
    from seshi.tui.styles import theme_css
    from seshi.themes import get_theme
    css = theme_css(get_theme("coral"))
    lines = css.split("\n")
    in_preview = False
    for line in lines:
        if "#preview" in line and "{" in line:
            in_preview = True
        if in_preview and "width:" in line:
            assert "3fr" in line
            break
        if in_preview and "}" in line:
            in_preview = False
    else:
        assert False, "Did not find width in #preview CSS block"
