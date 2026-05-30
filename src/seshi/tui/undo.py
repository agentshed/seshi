from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UndoEntry:
    action: str
    description: str
    sql_statements: list[tuple[str, tuple]] = field(default_factory=list)
    session_ids: list[str] = field(default_factory=list)


class UndoStack:
    MAX_SIZE = 10

    def __init__(self):
        self._stack: list[UndoEntry] = []

    def push(self, entry: UndoEntry) -> None:
        self._stack.append(entry)
        if len(self._stack) > self.MAX_SIZE:
            self._stack.pop(0)

    def pop(self) -> UndoEntry | None:
        if not self._stack:
            return None
        return self._stack.pop()

    def __len__(self) -> int:
        return len(self._stack)

    @property
    def empty(self) -> bool:
        return len(self._stack) == 0
