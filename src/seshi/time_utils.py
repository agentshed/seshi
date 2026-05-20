import time


def relative_time(ts: int) -> str:
    now = int(time.time())
    delta = now - ts
    if delta < 0:
        return "just now"
    if delta < 60:
        return "just now"
    if delta < 3600:
        m = delta // 60
        return f"{m}m ago"
    if delta < 86400:
        h = delta // 3600
        return f"{h}h ago"
    if delta < 2 * 86400:
        return "yesterday"
    if delta < 60 * 86400:
        d = delta // 86400
        return f"{d}d ago"
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def time_bucket(ts: int) -> str:
    now = int(time.time())
    delta = now - ts
    if delta < 86400:
        return "today"
    if delta < 2 * 86400:
        return "yesterday"
    if delta < 7 * 86400:
        return "this week"
    if delta < 30 * 86400:
        return "this month"
    return "older"
