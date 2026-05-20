import os
from seshi.lang_detect import detect_language


def test_python_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    detect_language.cache_clear()
    assert detect_language(str(tmp_path)) == "py"


def test_go_mod(tmp_path):
    (tmp_path / "go.mod").touch()
    detect_language.cache_clear()
    assert detect_language(str(tmp_path)) == "go"


def test_rust_cargo(tmp_path):
    (tmp_path / "Cargo.toml").touch()
    detect_language.cache_clear()
    assert detect_language(str(tmp_path)) == "rs"


def test_typescript(tmp_path):
    (tmp_path / "package.json").touch()
    (tmp_path / "tsconfig.json").touch()
    detect_language.cache_clear()
    assert detect_language(str(tmp_path)) == "ts"


def test_javascript_no_tsconfig(tmp_path):
    (tmp_path / "package.json").touch()
    detect_language.cache_clear()
    assert detect_language(str(tmp_path)) == "js"


def test_git_fallback(tmp_path):
    (tmp_path / ".git").mkdir()
    detect_language.cache_clear()
    assert detect_language(str(tmp_path)) == "git"


def test_nonexistent_dir():
    detect_language.cache_clear()
    assert detect_language("/nonexistent/path/xyz") == ""
