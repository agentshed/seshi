from seshi.cost import estimate_cost, format_usd, _get_rate, FALLBACK_RATE


def test_opus_rate():
    rate = _get_rate("claude-opus-4")
    assert rate == (15.0, 75.0)


def test_sonnet_rate():
    rate = _get_rate("claude-sonnet-4-6")
    assert rate == (3.0, 15.0)


def test_haiku_rate():
    rate = _get_rate("claude-haiku-4-5")
    assert rate == (1.0, 5.0)


def test_unknown_model_fallback():
    assert _get_rate("unknown-model") == FALLBACK_RATE


def test_none_model_fallback():
    assert _get_rate(None) == FALLBACK_RATE


def test_estimate_cost_basic():
    cost = estimate_cost(1_000_000, "claude-sonnet-4")
    expected = (250_000 * 3.0 + 750_000 * 15.0) / 1_000_000
    assert abs(cost - expected) < 0.001


def test_format_usd_tiny():
    assert format_usd(0.005) == "<$0.01"


def test_format_usd_large():
    assert format_usd(1234.5) == "$1,234"
