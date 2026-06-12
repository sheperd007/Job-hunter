"""LLM price map (USD per 1M tokens) and cost calculation. Pure, no I/O.

Update PRICE_MAP when provider prices change.
"""

# (input_per_million, output_per_million)
PRICE_MAP: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
}


def cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost of one call. Raises KeyError on unknown model (fail loud)."""
    inp, out = PRICE_MAP[model]
    return (prompt_tokens / 1_000_000) * inp + (completion_tokens / 1_000_000) * out
