import re


# Keep in sync with the inline copy in hook/hook.sh
_SYSTEM_BLOCK_RE = re.compile(
    r"<(local-command-caveat|system-reminder|command-name|command-message"
    r"|command-args|local-command-stdout|task-notification)"
    r"(?:\s[^>]*)?>.*?</\1>",
    re.DOTALL,
)

_MARKUP_TAG_RE = re.compile(
    r"</?[A-Za-z][A-Za-z0-9:_-]*(?:\s+[^<>]*)?/?>|<![^<>]*>"
)


def strip_system_blocks(text: str) -> str:
    return _SYSTEM_BLOCK_RE.sub("", text).strip()


def strip_markup_tags(text: str) -> str:
    return _MARKUP_TAG_RE.sub("", text)
