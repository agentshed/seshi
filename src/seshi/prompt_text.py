import re


_MARKUP_TAG_RE = re.compile(
    r"</?[A-Za-z][A-Za-z0-9:_-]*(?:\s+[^<>]*)?/?>|<![^<>]*>"
)


def strip_markup_tags(text: str) -> str:
    return _MARKUP_TAG_RE.sub("", text)
