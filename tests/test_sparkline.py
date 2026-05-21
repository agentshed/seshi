"""Tests for the sparkline log-scaling in OverviewView."""

import math

from seshi.tui.overview import SPARK_CHARS


def _spark_idx(v: int, max_val: int) -> int:
    """Replicate the sparkline index calculation from OverviewView."""
    if v == 0:
        return 0
    return int(math.log1p(v) / math.log1p(max_val) * (len(SPARK_CHARS) - 1))


def test_sparkline_skewed_data():
    """Non-zero days should map to visible spark characters even with outliers."""
    days = [1, 2, 0, 5, 0, 193]
    max_val = max(days)
    for v in days:
        idx = _spark_idx(v, max_val)
        if v > 0:
            assert idx > 0, f"Day with {v} sessions should be visible (idx={idx})"
        else:
            assert idx == 0


def test_sparkline_all_zeros():
    """All-zero input should produce all index 0."""
    days = [0] * 30
    max_val = max(days) if days else 1
    for v in days:
        assert _spark_idx(v, max(max_val, 1)) == 0


def test_sparkline_uniform():
    """Uniform non-zero input should produce identical indices."""
    days = [5, 5, 5, 5]
    max_val = max(days)
    indices = [_spark_idx(v, max_val) for v in days]
    assert len(set(indices)) == 1
    assert indices[0] == len(SPARK_CHARS) - 1  # max maps to highest char


def test_sparkline_single_value():
    """A single non-zero value should get the max index."""
    idx = _spark_idx(10, 10)
    assert idx == len(SPARK_CHARS) - 1


def test_sparkline_preserves_ordering():
    """Larger values should map to equal or higher indices."""
    days = [1, 3, 10, 50, 200]
    max_val = max(days)
    indices = [_spark_idx(v, max_val) for v in days]
    for i in range(len(indices) - 1):
        assert indices[i] <= indices[i + 1], (
            f"idx({days[i]})={indices[i]} > idx({days[i+1]})={indices[i+1]}"
        )
