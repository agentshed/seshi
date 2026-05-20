import sqlite3
from seshi.db import open_db, init_schema, get_setting, set_setting, DEFAULT_SETTINGS


def test_schema_creation(tmp_path):
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t["name"] for t in tables]
        assert "sessions" in names
        assert "tags" in names
        assert "settings" in names
        assert "project_favorites" in names


def test_wal_mode(tmp_path):
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


def test_foreign_keys_enabled(tmp_path):
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1


def test_default_settings_seeded(tmp_path):
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        for key, expected in DEFAULT_SETTINGS.items():
            val = get_setting(conn, key)
            assert val == expected, f"{key}: expected {expected}, got {val}"


def test_set_and_get_setting(tmp_path):
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        set_setting(conn, "theme", "nord")
        assert get_setting(conn, "theme") == "nord"


def test_context_manager_closes(tmp_path):
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        conn.execute("SELECT 1")
    with open_db(db_path) as conn2:
        result = conn2.execute("SELECT 1").fetchone()
        assert result[0] == 1
