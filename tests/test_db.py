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


def test_prompts_table_created(tmp_path):
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t["name"] for t in tables]
        assert "prompts" in names


def test_prompt_index_meta_table_created(tmp_path):
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t["name"] for t in tables]
        assert "prompt_index_meta" in names


def test_prompts_foreign_key(tmp_path):
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        try:
            conn.execute(
                "INSERT INTO prompts (session_id, prompt_index, text) VALUES (?, ?, ?)",
                ("nonexistent-session", 0, "hello"),
            )
            conn.commit()
            assert False, "Expected foreign key error"
        except sqlite3.IntegrityError:
            pass


def test_prompts_unique_constraint(tmp_path):
    import time
    db_path = tmp_path / "test.db"
    with open_db(db_path) as conn:
        now = int(time.time())
        conn.execute(
            "INSERT INTO sessions (session_id, cwd, launch_argv_json, created_at, last_activity_at) VALUES (?,?,?,?,?)",
            ("s1", "/tmp", "[]", now, now),
        )
        conn.execute(
            "INSERT INTO prompts (session_id, prompt_index, text) VALUES (?, ?, ?)",
            ("s1", 0, "hello"),
        )
        conn.commit()
        try:
            conn.execute(
                "INSERT INTO prompts (session_id, prompt_index, text) VALUES (?, ?, ?)",
                ("s1", 0, "duplicate"),
            )
            conn.commit()
            assert False, "Expected unique constraint error"
        except sqlite3.IntegrityError:
            pass
