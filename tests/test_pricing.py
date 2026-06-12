import pytest
from worker.pricing import cost, PRICE_MAP


def test_cost_known_model():
    # gpt-4.1-mini: $0.40 / 1M input, $1.60 / 1M output
    c = cost("gpt-4.1-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert c == pytest.approx(0.40 + 1.60)


def test_cost_partial_tokens():
    c = cost("gpt-4.1-mini", prompt_tokens=500_000, completion_tokens=0)
    assert c == pytest.approx(0.20)


def test_unknown_model_raises():
    with pytest.raises(KeyError):
        cost("nonexistent-model", 100, 100)


def test_price_map_has_required_models():
    assert "gpt-4.1-mini" in PRICE_MAP
    assert "gpt-4.1" in PRICE_MAP
