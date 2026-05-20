import os
from functools import lru_cache

MANIFEST_MAP = [
    ("Cargo.toml", "rs"),
    ("go.mod", "go"),
    ("pyproject.toml", "py"),
    ("requirements.txt", "py"),
    ("setup.py", "py"),
    ("Gemfile", "rb"),
    ("deno.json", "dn"),
    ("deno.jsonc", "dn"),
    ("pom.xml", "jv"),
    ("build.gradle", "jv"),
]


@lru_cache(maxsize=256)
def detect_language(cwd: str) -> str:
    if not os.path.isdir(cwd):
        return ""

    for manifest, tag in MANIFEST_MAP:
        if os.path.exists(os.path.join(cwd, manifest)):
            if tag == "py":
                return "py"
            if manifest in ("pyproject.toml", "requirements.txt", "setup.py"):
                return "py"
            return tag

    has_package_json = os.path.exists(os.path.join(cwd, "package.json"))
    has_tsconfig = os.path.exists(os.path.join(cwd, "tsconfig.json"))
    if has_package_json and has_tsconfig:
        return "ts"
    if has_package_json:
        return "js"

    if os.path.isdir(os.path.join(cwd, ".git")):
        return "git"

    return ""
