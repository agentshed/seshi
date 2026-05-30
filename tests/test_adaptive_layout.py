"""Tests for adaptive preview layout (Phase B, Item 6)."""
import time
from unittest.mock import MagicMock, patch, PropertyMock

from textual.geometry import Size

from seshi.tui.app import SeshiApp
from seshi.tui.preview import Preview
from seshi.tui.footer import Footer


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


def test_preview_hidden_at_narrow_width(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="test-session")
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview.display = True

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(80, 24)):
            app._update_preview_layout()

    assert app._preview.display is False
    assert app._sessions_list.styles.width == "1fr"


def test_preview_visible_at_wide_width(tmp_db):
    _insert_session(tmp_db, "s1", custom_name="test-session")
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview.display = False

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(120, 40)):
            app._update_preview_layout()

    assert app._preview.display is True
    assert app._sessions_list.styles.width == 48  # int(120 * 0.4)


def test_preview_proportional_width(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(200, 50)):
            app._update_preview_layout()

    assert app._sessions_list.styles.width == 80  # int(200 * 0.4)
    assert app._preview.display is True


def test_preview_minimum_list_width(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview_user_override = True

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(60, 20)):
            app._update_preview_layout()

    assert app._sessions_list.styles.width == 30  # max(30, int(60 * 0.4))
    assert app._preview.display is True


def test_manual_override_forces_show(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview_user_override = True

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(80, 24)):
            app._update_preview_layout()

    assert app._preview.display is True


def test_manual_override_forces_hide(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview_user_override = False

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(200, 50)):
            app._update_preview_layout()

    assert app._preview.display is False
    assert app._sessions_list.styles.width == "1fr"


def test_resize_resets_override(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview_user_override = True

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer), \
         patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(120, 40)):
        app.on_resize(MagicMock())

    assert app._preview_user_override is None


def test_resize_auto_hides_at_narrow(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer), \
         patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(80, 24)):
        app.on_resize(MagicMock())

    assert app._preview.display is False


def test_resize_does_not_update_in_non_sessions_view(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview.display = True

    with patch.object(SeshiApp, "watch_current_view"):
        app.current_view = "overview"

    with patch.object(app, "_update_preview_layout") as mock_layout:
        app.on_resize(MagicMock())
        mock_layout.assert_not_called()


def test_footer_updated_with_preview_state(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()

    mock_footer = MagicMock(spec=Footer)
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(80, 24)):
            app._update_preview_layout()

    assert mock_footer.preview_visible is False


def test_footer_preview_label_when_hidden():
    footer = Footer()
    footer.view = "sessions"
    footer.preview_visible = False
    rendered = footer.render().plain
    assert "hidden" in rendered


def test_footer_preview_label_when_visible():
    footer = Footer()
    footer.view = "sessions"
    footer.preview_visible = True
    rendered = footer.render().plain
    assert "preview" in rendered


def test_layout_boundary_at_100_width(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(100, 30)):
            app._update_preview_layout()
    assert app._preview.display is True

    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(99, 30)):
            app._preview_user_override = None
            app._update_preview_layout()
    assert app._preview.display is False


def test_layout_skips_without_preview(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._update_preview_layout()


def test_layout_defaults_to_120_when_size_unknown(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(0, 0)):
            app._update_preview_layout()

    assert app._preview.display is True
    assert app._sessions_list.styles.width == 48  # int(120 * 0.4)
