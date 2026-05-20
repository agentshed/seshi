import json
import os
import stat
from unittest import mock

from seshi.hook_manager import install_hook
from seshi.settings import patch_settings, unpatch_settings


def test_install_hook_creates_executable(tmp_path):
    hook_path = tmp_path / "hook.sh"
    with mock.patch("seshi.hook_manager.SESHI_DIR", tmp_path), \
         mock.patch("seshi.hook_manager.HOOK_PATH", hook_path):
        install_hook()
    assert hook_path.exists()
    mode = hook_path.stat().st_mode
    assert mode & stat.S_IXUSR


def test_patch_settings_adds_entries(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")
    hook_path = tmp_path / "hook.sh"
    with mock.patch("seshi.settings.CLAUDE_SETTINGS", settings_path), \
         mock.patch("seshi.settings.HOOK_PATH", hook_path):
        patch_settings()
    data = json.loads(settings_path.read_text())
    assert "SessionStart" in data["hooks"]
    assert "Stop" in data["hooks"]


def test_patch_settings_idempotent(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")
    hook_path = tmp_path / "hook.sh"
    with mock.patch("seshi.settings.CLAUDE_SETTINGS", settings_path), \
         mock.patch("seshi.settings.HOOK_PATH", hook_path):
        patch_settings()
        patch_settings()
    data = json.loads(settings_path.read_text())
    assert len(data["hooks"]["SessionStart"]) == 1
    assert len(data["hooks"]["Stop"]) == 1


def test_unpatch_settings_removes_entries(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")
    hook_path = tmp_path / "hook.sh"
    with mock.patch("seshi.settings.CLAUDE_SETTINGS", settings_path), \
         mock.patch("seshi.settings.HOOK_PATH", hook_path):
        patch_settings()
        unpatch_settings()
    data = json.loads(settings_path.read_text())
    assert "hooks" not in data


def test_unpatch_missing_file(tmp_path):
    settings_path = tmp_path / "nonexistent.json"
    with mock.patch("seshi.settings.CLAUDE_SETTINGS", settings_path):
        unpatch_settings()
