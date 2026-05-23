import sqlite3
from contextlib import contextmanager
from pathlib import Path

from seshi.paths import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id        TEXT PRIMARY KEY,
    cwd               TEXT NOT NULL,
    launch_argv_json  TEXT NOT NULL DEFAULT '[]',
    env_json          TEXT,
    git_branch        TEXT,
    git_sha           TEXT,
    first_prompt      TEXT,
    custom_name       TEXT,
    is_favorite       INTEGER NOT NULL DEFAULT 0,
    is_archived       INTEGER NOT NULL DEFAULT 0,
    is_backfilled     INTEGER NOT NULL DEFAULT 0,
    message_count     INTEGER NOT NULL DEFAULT 0,
    token_count       INTEGER NOT NULL DEFAULT 0,
    status            TEXT,
    created_at        INTEGER NOT NULL,
    last_activity_at  INTEGER NOT NULL,
    origin_host       TEXT,
    schema_version    INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_sessions_last_activity ON sessions (last_activity_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_cwd ON sessions (cwd);
CREATE INDEX IF NOT EXISTS idx_sessions_favorite ON sessions (is_favorite) WHERE is_favorite = 1;

CREATE TABLE IF NOT EXISTS tags (
    session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (session_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags (tag);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE TABLE IF NOT EXISTS project_favorites (
    cwd          TEXT PRIMARY KEY,
    custom_name  TEXT
);
"""

DEFAULT_SETTINGS = {
    "prune_days": "0",
    "hide_missing_dirs": "0",
    "hide_stale_sessions": "1",
    "delete_jsonl_with_session": "ask",
    "accent_color": "#D97757",
    "theme": "coral",
    "sort_mode": "frecency",
    "schema_version": "1",
}


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    for col, defn in [
        ("resume_count", "INTEGER NOT NULL DEFAULT 0"),
        ("frecency_rank", "REAL NOT NULL DEFAULT 1.0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {defn}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


@contextmanager
def open_db(path: Path | None = None, readonly: bool = False):
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row:
        return row["value"]
    return DEFAULT_SETTINGS.get(key)


def record_resume(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute(
        "UPDATE sessions SET resume_count = resume_count + 1, frecency_rank = frecency_rank + 1.0 WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
