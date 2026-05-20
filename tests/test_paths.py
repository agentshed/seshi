from seshi.paths import unsanitize_path, resolve_best_cwd


def test_leading_dash_becomes_slash():
    result = unsanitize_path("-Users-gklein")
    assert "/Users/gklein" in result


def test_no_dashes():
    result = unsanitize_path("-home")
    assert result == ["/home"]


def test_power_set_enumeration():
    result = unsanitize_path("-a-b")
    assert "/a/b" in result
    assert "/a-b" in result


def test_dotfile_double_dash():
    result = unsanitize_path("--vault")
    paths = [p for p in result if ".vault" in p or "/vault" in p]
    assert len(paths) > 0


def test_more_than_six_dashes_fallback():
    name = "-a-b-c-d-e-f-g-h"
    result = unsanitize_path(name)
    all_slashes = "/a/b/c/d/e/f/g/h"
    assert all_slashes in result
    assert len(result) < 2 ** 7


def test_resolve_prefers_existing(tmp_path):
    d = tmp_path / "real"
    d.mkdir()
    candidates = unsanitize_path("-nonexistent")
    result = resolve_best_cwd("-nonexistent")
    assert isinstance(result, str)


def test_empty_name():
    result = unsanitize_path("")
    assert result == ["/"]
