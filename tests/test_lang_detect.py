import pytest
from seshi.lang_detect import detect_language


@pytest.fixture(autouse=True)
def _clear_cache():
    detect_language.cache_clear()


def test_python_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").touch()
    assert detect_language(str(tmp_path)) == "py"


def test_python_requirements(tmp_path):
    (tmp_path / "requirements.txt").touch()
    assert detect_language(str(tmp_path)) == "py"


def test_python_setup_cfg(tmp_path):
    (tmp_path / "setup.cfg").touch()
    assert detect_language(str(tmp_path)) == "py"


def test_go_mod(tmp_path):
    (tmp_path / "go.mod").touch()
    assert detect_language(str(tmp_path)) == "go"


def test_go_sum(tmp_path):
    (tmp_path / "go.sum").touch()
    assert detect_language(str(tmp_path)) == "go"


def test_rust_cargo(tmp_path):
    (tmp_path / "Cargo.toml").touch()
    assert detect_language(str(tmp_path)) == "rs"


def test_rust_cargo_lock(tmp_path):
    (tmp_path / "Cargo.lock").touch()
    assert detect_language(str(tmp_path)) == "rs"


def test_ruby_gemfile(tmp_path):
    (tmp_path / "Gemfile").touch()
    assert detect_language(str(tmp_path)) == "rb"


def test_ruby_gemfile_lock(tmp_path):
    (tmp_path / "Gemfile.lock").touch()
    assert detect_language(str(tmp_path)) == "rb"


def test_deno_json(tmp_path):
    (tmp_path / "deno.json").touch()
    assert detect_language(str(tmp_path)) == "dn"


def test_deno_jsonc(tmp_path):
    (tmp_path / "deno.jsonc").touch()
    assert detect_language(str(tmp_path)) == "dn"


def test_java_pom(tmp_path):
    (tmp_path / "pom.xml").touch()
    assert detect_language(str(tmp_path)) == "jv"


def test_java_gradle(tmp_path):
    (tmp_path / "build.gradle").touch()
    assert detect_language(str(tmp_path)) == "jv"


def test_kotlin_gradle_kts(tmp_path):
    (tmp_path / "build.gradle.kts").touch()
    assert detect_language(str(tmp_path)) == "kt"


def test_swift(tmp_path):
    (tmp_path / "Package.swift").touch()
    assert detect_language(str(tmp_path)) == "sw"


def test_elixir(tmp_path):
    (tmp_path / "mix.exs").touch()
    assert detect_language(str(tmp_path)) == "ex"


def test_dart(tmp_path):
    (tmp_path / "pubspec.yaml").touch()
    assert detect_language(str(tmp_path)) == "drt"


def test_zig(tmp_path):
    (tmp_path / "build.zig").touch()
    assert detect_language(str(tmp_path)) == "zig"


def test_haskell(tmp_path):
    (tmp_path / "stack.yaml").touch()
    assert detect_language(str(tmp_path)) == "hs"


def test_php(tmp_path):
    (tmp_path / "composer.json").touch()
    assert detect_language(str(tmp_path)) == "php"


def test_cpp_cmake(tmp_path):
    (tmp_path / "CMakeLists.txt").touch()
    assert detect_language(str(tmp_path)) == "cpp"


def test_typescript(tmp_path):
    (tmp_path / "package.json").touch()
    (tmp_path / "tsconfig.json").touch()
    assert detect_language(str(tmp_path)) == "ts"


def test_javascript_no_tsconfig(tmp_path):
    (tmp_path / "package.json").touch()
    assert detect_language(str(tmp_path)) == "js"


def test_git_fallback(tmp_path):
    (tmp_path / ".git").mkdir()
    assert detect_language(str(tmp_path)) == "git"


def test_nonexistent_dir():
    assert detect_language("/nonexistent/path/xyz") == ""


def test_empty_directory(tmp_path):
    assert detect_language(str(tmp_path)) == ""


def test_priority_rust_over_python(tmp_path):
    (tmp_path / "Cargo.toml").touch()
    (tmp_path / "requirements.txt").touch()
    assert detect_language(str(tmp_path)) == "rs"


def test_priority_gradle_over_gradle_kts(tmp_path):
    (tmp_path / "build.gradle").touch()
    (tmp_path / "build.gradle.kts").touch()
    assert detect_language(str(tmp_path)) == "jv"
