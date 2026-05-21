from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class CapturedScreen:
    raw: str
    lines: list[str] = field(init=False)

    def __post_init__(self):
        self.lines = self.raw.split("\n")

    def __contains__(self, item: str) -> bool:
        return item in self.raw

    def __str__(self) -> str:
        return self.raw

    def line_containing(self, text: str) -> str | None:
        for line in self.lines:
            if text in line:
                return line
        return None

    def lines_containing(self, text: str) -> list[str]:
        return [line for line in self.lines if text in line]

    def count_lines_containing(self, text: str) -> int:
        return len(self.lines_containing(text))

    def line_at(self, index: int) -> str:
        if 0 <= index < len(self.lines):
            return self.lines[index]
        return ""

    def non_empty_lines(self) -> list[str]:
        return [line for line in self.lines if line.strip()]

    def matches(self, pattern: str) -> list[re.Match]:
        return list(re.finditer(pattern, self.raw))


class TmuxController:
    HEADER_PATTERN = "█▀▀ █▀▀ █▀▀"

    def __init__(
        self,
        session_name: str | None = None,
        width: int = 120,
        height: int = 40,
    ):
        self.session_name = session_name or f"seshi-test-{uuid.uuid4().hex[:8]}"
        self.width = width
        self.height = height
        self._started = False

    def start(self) -> None:
        subprocess.run(
            [
                "tmux", "new-session", "-d",
                "-s", self.session_name,
                "-x", str(self.width),
                "-y", str(self.height),
                "bash", "--norc", "--noprofile",
            ],
            check=True,
            capture_output=True,
        )
        self._started = True
        self._wait_for_shell_ready()

    def stop(self) -> None:
        if self._started:
            subprocess.run(
                ["tmux", "kill-session", "-t", self.session_name],
                capture_output=True,
            )
            self._started = False

    def _wait_for_shell_ready(self, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            screen = self.capture()
            if "$" in screen.raw:
                return
            time.sleep(0.2)

    def send_keys(self, *keys: str, delay: float = 0.0) -> None:
        for key in keys:
            subprocess.run(
                ["tmux", "send-keys", "-t", self.session_name, key],
                check=True,
                capture_output=True,
            )
            if delay > 0:
                time.sleep(delay)

    def send_text(self, text: str) -> None:
        for char in text:
            subprocess.run(
                ["tmux", "send-keys", "-t", self.session_name, "-l", char],
                check=True,
                capture_output=True,
            )

    def type_and_enter(self, text: str) -> None:
        self.send_text(text)
        self.send_keys("Enter")

    def capture(self) -> CapturedScreen:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", self.session_name, "-p"],
            capture_output=True,
            text=True,
            check=True,
        )
        return CapturedScreen(raw=result.stdout)

    def wait_for(
        self,
        text: str,
        timeout: float = 10.0,
        interval: float = 0.3,
    ) -> CapturedScreen:
        deadline = time.monotonic() + timeout
        last_screen = None
        while time.monotonic() < deadline:
            screen = self.capture()
            last_screen = screen
            if text in screen:
                return screen
            time.sleep(interval)
        raise TimeoutError(
            f"Timed out after {timeout}s waiting for '{text}'.\n"
            f"Last capture:\n{last_screen}"
        )

    def wait_for_pattern(
        self,
        pattern: str,
        timeout: float = 10.0,
        interval: float = 0.3,
    ) -> CapturedScreen:
        deadline = time.monotonic() + timeout
        last_screen = None
        while time.monotonic() < deadline:
            screen = self.capture()
            last_screen = screen
            if re.search(pattern, screen.raw):
                return screen
            time.sleep(interval)
        raise TimeoutError(
            f"Timed out after {timeout}s waiting for pattern '{pattern}'.\n"
            f"Last capture:\n{last_screen}"
        )

    def wait_for_absence(
        self,
        text: str,
        timeout: float = 5.0,
        interval: float = 0.3,
    ) -> CapturedScreen:
        deadline = time.monotonic() + timeout
        last_screen = None
        while time.monotonic() < deadline:
            screen = self.capture()
            last_screen = screen
            if text not in screen:
                return screen
            time.sleep(interval)
        raise TimeoutError(
            f"Timed out after {timeout}s waiting for '{text}' to disappear.\n"
            f"Last capture:\n{last_screen}"
        )

    def wait_for_tui(self, timeout: float = 15.0) -> CapturedScreen:
        return self.wait_for(self.HEADER_PATTERN, timeout=timeout)

    def launch_seshi(
        self,
        tmp_home: str,
        extra_args: str = "",
        extra_env: str = "",
    ) -> CapturedScreen:
        path = os.environ.get("PATH", "")
        self.send_keys(f"export PATH='{path}'", "Enter")
        time.sleep(0.2)

        cmd_parts = [f"HOME={tmp_home}"]
        if extra_env:
            cmd_parts.append(extra_env)
        cmd_parts.append("uv run seshi")
        if extra_args:
            cmd_parts.append(extra_args)
        cmd = " ".join(cmd_parts)

        self.send_keys(cmd, "Enter")
        return self.wait_for_tui()

    def resize(self, width: int, height: int) -> None:
        subprocess.run(
            [
                "tmux", "resize-window",
                "-t", self.session_name,
                "-x", str(width),
                "-y", str(height),
            ],
            check=True,
            capture_output=True,
        )
        self.width = width
        self.height = height

    @staticmethod
    def query_db(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        result = [dict(row) for row in rows]
        conn.close()
        return result
