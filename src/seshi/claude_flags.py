"""Persistent Claude Code CLI flag defaults.

Stores flags in the existing ``settings`` table with a ``claude.`` prefix.
Values are treated as dumb passthroughs — seshi never validates flag names
or values so any current or future Claude CLI flag works.

Value conventions:
- ``"true"`` → ``--flag`` (boolean)
- Comma-separated → ``--flag val1 --flag val2`` (repeated)
- Any other string → ``--flag value``
"""

from __future__ import annotations

import sqlite3

PREFIX = "claude."

DEFAULTS: dict[str, str] = {
    "permission-mode": "plan",
    "effort": "high",
}


def get_flags(conn: sqlite3.Connection) -> dict[str, str]:
    """Return all ``claude.*`` settings stripped of the prefix."""
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key LIKE ?", (PREFIX + "%",)
    ).fetchall()
    return {row["key"][len(PREFIX):]: row["value"] for row in rows}


def set_flag(conn: sqlite3.Connection, flag: str, value: str) -> None:
    """Store ``claude.<flag>`` = *value*."""
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (PREFIX + flag, value),
    )
    conn.commit()


def unset_flag(conn: sqlite3.Connection, flag: str) -> None:
    """Delete the ``claude.<flag>`` row."""
    conn.execute("DELETE FROM settings WHERE key = ?", (PREFIX + flag,))
    conn.commit()


def reset_flags(conn: sqlite3.Connection, flag: str | None = None) -> None:
    """Reset *flag* to its default (or remove if no default).

    If *flag* is ``None``, reset **all** claude flags.
    """
    if flag is not None:
        if flag in DEFAULTS:
            set_flag(conn, flag, DEFAULTS[flag])
        else:
            unset_flag(conn, flag)
    else:
        conn.execute("DELETE FROM settings WHERE key LIKE ?", (PREFIX + "%",))
        conn.commit()
        seed_defaults(conn)


def build_args(conn: sqlite3.Connection) -> list[str]:
    """Assemble stored flags into CLI args for ``claude``."""
    flags = get_flags(conn)
    args: list[str] = []
    for flag, value in sorted(flags.items()):
        if value == "true":
            args.append(f"--{flag}")
        elif "," in value:
            for v in value.split(","):
                args.extend([f"--{flag}", v])
        else:
            args.extend([f"--{flag}", value])
    return args


def seed_defaults(conn: sqlite3.Connection) -> None:
    """Seed default flags via ``INSERT OR IGNORE``."""
    for flag, value in DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (PREFIX + flag, value),
        )
    conn.commit()
