from seshi.shell_init import generate_wrapper, generate_completions, detect_shell, generate_init
from unittest import mock


def test_bash_wrapper_contains_eval():
    w = generate_wrapper("bash")
    assert "eval" in w
    assert "seshi()" in w or "seshi " in w


def test_zsh_wrapper_same_as_bash():
    assert generate_wrapper("zsh") == generate_wrapper("bash")


def test_fish_wrapper_is_function():
    w = generate_wrapper("fish")
    assert "function seshi" in w


def test_bash_completions_has_complete():
    c = generate_completions("bash")
    assert "complete" in c
    assert "compgen" in c


def test_zsh_completions_has_compdef():
    c = generate_completions("zsh")
    assert "compdef" in c
    assert "compadd" in c


def test_fish_completions_has_complete():
    c = generate_completions("fish")
    assert "complete -c seshi" in c


def test_detect_shell_zsh():
    with mock.patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
        assert detect_shell() == "zsh"


def test_detect_shell_default():
    with mock.patch.dict("os.environ", {"SHELL": "/bin/sh"}):
        assert detect_shell() == "bash"


def test_generate_init_full():
    output = generate_init("bash")
    assert "eval" in output
    assert "complete" in output


def test_generate_init_completions_only():
    output = generate_init("bash", completions_only=True)
    assert "eval" not in output
    assert "complete" in output
