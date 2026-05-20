import time
from seshi.time_utils import relative_time, time_bucket


def test_just_now():
    now = int(time.time())
    assert relative_time(now) == "just now"


def test_minutes_ago():
    ts = int(time.time()) - 300
    assert "5m ago" == relative_time(ts)


def test_hours_ago():
    ts = int(time.time()) - 7200
    assert "2h ago" == relative_time(ts)


def test_yesterday():
    ts = int(time.time()) - 100000
    assert relative_time(ts) == "yesterday"


def test_days_ago():
    ts = int(time.time()) - 5 * 86400
    assert "5d ago" == relative_time(ts)


def test_bucket_today():
    ts = int(time.time()) - 3600
    assert time_bucket(ts) == "today"


def test_bucket_this_week():
    ts = int(time.time()) - 3 * 86400
    assert time_bucket(ts) == "this week"


def test_bucket_older():
    ts = int(time.time()) - 60 * 86400
    assert time_bucket(ts) == "older"
