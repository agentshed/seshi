import os


def detect_shell() -> str:
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    if "fish" in shell:
        return "fish"
    return "bash"


def generate_wrapper(shell: str) -> str:
    if shell == "fish":
        return _fish_wrapper()
    return _posix_wrapper()


def generate_completions(shell: str) -> str:
    if shell == "zsh":
        return _zsh_completions()
    if shell == "fish":
        return _fish_completions()
    return _bash_completions()


def _posix_wrapper() -> str:
    return r"""
seshi() {
    local output
    output="$(command seshi "$@")"
    local rc=$?
    if [ -z "$output" ]; then
        return $rc
    fi
    case "$output" in
        cd\ *\&\&\ exec\ *)
            eval "$output"
            ;;
        *)
            printf '%s\n' "$output"
            ;;
    esac
    return $rc
}
""".strip() + "\n"


def _fish_wrapper() -> str:
    return r"""
function seshi
    set -l output (command seshi $argv)
    set -l rc $status
    if test -z "$output"
        return $rc
    end
    switch "$output"
        case 'cd *&& exec *'
            eval $output
        case '*'
            printf '%s\n' $output
    end
    return $rc
end
""".strip() + "\n"


def _bash_completions() -> str:
    return r"""
_seshi_completions() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local words=$(command seshi init --completions 2>/dev/null)
    COMPREPLY=($(compgen -W "$words" -- "$cur"))
}
complete -F _seshi_completions seshi
""".strip() + "\n"


def _zsh_completions() -> str:
    return r"""
_seshi() {
    if (( ! $+functions[compinit] )); then
        autoload -Uz compinit && compinit
    fi
    local words=$(command seshi init --completions 2>/dev/null)
    compadd -- ${=words}
}
compdef _seshi seshi
""".strip() + "\n"


def _fish_completions() -> str:
    return r"""
complete -c seshi -f -a "(command seshi init --completions 2>/dev/null)"
""".strip() + "\n"


def generate_init(shell: str, completions_only: bool = False) -> str:
    if completions_only:
        return generate_completions(shell)
    return generate_wrapper(shell) + "\n" + generate_completions(shell)
