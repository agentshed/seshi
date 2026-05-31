import filecmp
import importlib.resources
import os
import shutil

from seshi.paths import SESHI_DIR, HOOK_PATH
from seshi.settings import patch_settings, unpatch_settings


def install_hook() -> None:
    SESHI_DIR.mkdir(parents=True, exist_ok=True)
    src = importlib.resources.files("seshi").joinpath("hook/hook.sh")
    with importlib.resources.as_file(src) as src_path:
        shutil.copy2(str(src_path), str(HOOK_PATH))
    os.chmod(str(HOOK_PATH), 0o755)


def hook_is_current() -> bool:
    if not HOOK_PATH.exists():
        return False
    src = importlib.resources.files("seshi").joinpath("hook/hook.sh")
    with importlib.resources.as_file(src) as src_path:
        return filecmp.cmp(str(src_path), str(HOOK_PATH), shallow=False)


def hook_needs_update() -> str | None:
    if not HOOK_PATH.exists():
        return "is not installed"
    if not hook_is_current():
        return "is outdated"
    return None


def uninstall_hook() -> None:
    unpatch_settings()
    if HOOK_PATH.exists():
        HOOK_PATH.unlink()
