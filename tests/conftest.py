import sqlite3
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from seshi.db import init_schema, set_setting

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    set_setting(conn, "hide_stale_sessions", "0")
    yield conn
    conn.close()
