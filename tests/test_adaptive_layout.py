"""Tests for adaptive preview layout with multi-mode cycling."""
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


def test_default_mode_is_normal(tmp_db):
    app = SeshiApp(conn=tmp_db)
    assert app._preview_mode == "normal"


def test_mode_normal_width_allocation(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(120, 40)):
            app._update_preview_layout()

    assert app._preview.display is True
    assert app._sessions_list.styles.width == 60  # int(120 * 0.5)


def test_mode_min_width_allocation(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview_mode = "min"

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(120, 40)):
            app._update_preview_layout()

    assert app._preview.display is True
    assert app._sessions_list.styles.width == 105  # int(120 * 0.875)


def test_mode_max_width_allocation(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview_mode = "max"

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(120, 40)):
            app._update_preview_layout()

    assert app._preview.display is True
    assert app._sessions_list.styles.width == 48  # int(120 * 0.4)


def test_mode_off_hides_preview(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview_mode = "off"

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(200, 50)):
            app._update_preview_layout()

    assert app._preview.display is False
    assert app._sessions_list.styles.width == "1fr"


def test_minimum_list_width_enforced(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(50, 20)):
            app._update_preview_layout()

    assert app._sessions_list.styles.width == 30  # max(30, int(50 * 0.5))
    assert app._preview.display is True


def test_proportional_width_at_200(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(200, 50)):
            app._update_preview_layout()

    assert app._sessions_list.styles.width == 100  # int(200 * 0.5)
    assert app._preview.display is True


def test_resize_preserves_mode(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview_mode = "max"

    mock_footer = MagicMock()
    with patch.object(app, "query_one", return_value=mock_footer), \
         patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(120, 40)):
        app.on_resize(MagicMock())

    assert app._preview_mode == "max"
    assert app._preview.display is True
    assert app._sessions_list.styles.width == 48  # int(120 * 0.4)


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


def test_footer_updated_with_preview_mode(tmp_db):
    app = SeshiApp(conn=tmp_db)
    app._sessions_list = MagicMock()
    app._preview = MagicMock()
    app._preview_mode = "min"

    mock_footer = MagicMock(spec=Footer)
    with patch.object(app, "query_one", return_value=mock_footer):
        with patch.object(type(app), "size", new_callable=PropertyMock, return_value=Size(120, 40)):
            app._update_preview_layout()

    assert mock_footer.preview_mode == "min"


def test_footer_label_hidden():
    footer = Footer()
    footer.view = "sessions"
    footer.preview_mode = "off"
    rendered = footer.render().plain
    assert "hidden" in rendered


def test_footer_label_normal():
    footer = Footer()
    footer.view = "sessions"
    footer.preview_mode = "normal"
    rendered = footer.render().plain
    assert "preview" in rendered
    assert "min" not in rendered
    assert "max" not in rendered


def test_footer_label_min():
    footer = Footer()
    footer.view = "sessions"
    footer.preview_mode = "min"
    rendered = footer.render().plain
    assert "preview:min" in rendered


def test_footer_label_max():
    footer = Footer()
    footer.view = "sessions"
    footer.preview_mode = "max"
    rendered = footer.render().plain
    assert "preview:max" in rendered


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
    assert app._sessions_list.styles.width == 60  # int(120 * 0.5)
