MODEL_RATES: dict[str, tuple[float, float]] = {
    "claude-opus-4": (15.0, 75.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-opus-4-5": (15.0, 75.0),
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.80, 4.0),
}

FALLBACK_RATE = (3.0, 15.0)


def _get_rate(model: str | None) -> tuple[float, float]:
    if not model:
        return FALLBACK_RATE
    for key, rate in MODEL_RATES.items():
        if key in model:
            return rate
    return FALLBACK_RATE


def estimate_cost(token_count: int, model: str | None = None) -> float:
    input_rate, output_rate = _get_rate(model)
    input_tokens = token_count * 0.25
    output_tokens = token_count * 0.75
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def format_usd(amount: float) -> str:
    if amount < 0.01:
        return "<$0.01"
    if amount < 100:
        return f"${amount:.2f}"
    return f"${amount:,.0f}"
