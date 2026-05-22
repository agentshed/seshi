import sqlite3
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from seshi.db import init_schema

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    conn.execute("UPDATE settings SET value = '0' WHERE key = 'hide_stale_sessions'")
    conn.commit()
    yield conn
    conn.close()
