from dataclasses import dataclass
import sqlite3


@dataclass
class Session:
    session_id: str
    cwd: str
    launch_argv_json: str
    env_json: str | None
    git_branch: str | None
    git_sha: str | None
    first_prompt: str | None
    custom_name: str | None
    is_favorite: int
    is_archived: int
    is_backfilled: int
    message_count: int
    token_count: int
    status: str | None
    created_at: int
    last_activity_at: int
    origin_host: str | None
    schema_version: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Session":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class Tag:
    session_id: str
    tag: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Tag":
        return cls(session_id=row["session_id"], tag=row["tag"])


@dataclass
class ProjectFavorite:
    cwd: str
    custom_name: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ProjectFavorite":
        return cls(cwd=row["cwd"], custom_name=row["custom_name"])
