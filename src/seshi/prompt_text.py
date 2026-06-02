import re


# Keep in sync with the inline copy in hook/hook.sh
_SYSTEM_BLOCK_RE = re.compile(
    r"<(local-command-caveat|local-command-stdout|local-command-stderr"
    r"|system-reminder|command-name|command-message|command-args"
    r"|bash-input|bash-stdout|bash-stderr"
    r"|task-notification)"
    r"(?:\s[^>]*)?>.*?</\1>",
    re.DOTALL,
)

_MARKUP_TAG_RE = re.compile(
    r"</?[A-Za-z][A-Za-z0-9:_-]*(?:\s+[^<>]*)?/?>|<![^<>]*>"
)

_COMMAND_NAME_RE = re.compile(
    r"<command-name>(.*?)</command-name>", re.DOTALL
)
_COMMAND_ARGS_RE = re.compile(
    r"<command-args>(.*?)</command-args>", re.DOTALL
)
_COMMAND_MESSAGE_RE = re.compile(
    r"<command-message>.*?</command-message>", re.DOTALL
)


def extract_command_text(text: str) -> str | None:
    """Extract slash-command invocation as readable text.

    Given XML like:
        <command-name>/foo</command-name>
        <command-message>foo</command-message>
        <command-args>bar baz</command-args>

    Returns: "/foo bar baz"
    """
    name_m = _COMMAND_NAME_RE.search(text)
    if not name_m:
        return None
    name = name_m.group(1).strip()
    args_m = _COMMAND_ARGS_RE.search(text)
    args = args_m.group(1).strip() if args_m else ""
    if args:
        return f"{name} {args}"
    return name if name else None


def replace_command_tags(text: str) -> str:
    """Replace command XML tags with readable text inline.

    Replaces <command-name> and <command-args> with their content,
    removes <command-message> (redundant), then returns the result.
    Other system block tags are left for strip_system_blocks().
    """
    cmd_text = extract_command_text(text)
    if cmd_text is None:
        return text
    # Replace the first command-name tag with the full command text
    result = _COMMAND_NAME_RE.sub(cmd_text, text, count=1)
    # Remove remaining command-name tags (if any)
    result = _COMMAND_NAME_RE.sub("", result)
    # Remove command-args and command-message tags entirely
    result = _COMMAND_ARGS_RE.sub("", result)
    result = _COMMAND_MESSAGE_RE.sub("", result)
    return result


def strip_system_blocks(text: str) -> str:
    return _SYSTEM_BLOCK_RE.sub("", text).strip()


def strip_markup_tags(text: str) -> str:
    return _MARKUP_TAG_RE.sub("", text)
