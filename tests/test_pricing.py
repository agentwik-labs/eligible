from decimal import Decimal

import pytest

from eligible.llm import pricing
from eligible.llm.types import Usage


def test_sonnet_cost_matches_hand_math() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=100_000)
    # $2/MTok in + $10/MTok out
    assert pricing.cost_usd("claude-sonnet-5-5", usage) == Decimal("3.00")


def test_cache_write_costs_more_and_cache_read_costs_less() -> None:
    write = Usage(cache_write_5m_tokens=1_000_000)
    read = Usage(cache_read_tokens=1_000_000)
    assert pricing.cost_usd("claude-sonnet-5-5", write) == Decimal("2.50")  # 1.25x
    assert pricing.cost_usd("claude-sonnet-5-5", read) == Decimal("0.20")
    assert pricing.cost_usd("claude-sonnet-5-5", Usage(cache_write_1h_tokens=1_000_000)) == 4


def test_prompt_cache_savings_against_uncached_baseline() -> None:
    usage = Usage(input_tokens=500, cache_read_tokens=9_500, output_tokens=0)
    cached = pricing.cost_usd("claude-sonnet-5-5", usage)
    uncached = pricing.uncached_cost_usd("claude-sonnet-5-5", usage)
    assert uncached == Decimal("0.02")
    assert cached < uncached / 5


def test_haiku_switches_to_long_context_rate_past_100k_prompt_tokens() -> None:
    short = Usage(input_tokens=100_000)
    long = Usage(input_tokens=100_001)
    assert pricing.cost_usd("claude-haiku-5-5", short) == Decimal("0.01")
    assert pricing.cost_usd("claude-haiku-5-5", long) == Decimal("0.050000500")
    # cache reads count toward the threshold, so the whole request reprices
    mixed = Usage(input_tokens=1_000, cache_read_tokens=100_000)
    assert pricing.cost_usd("claude-haiku-5-5", mixed) > pricing.cost_usd(
        "claude-haiku-5-5", Usage(input_tokens=1_000)
    ) + Decimal("0.001")


def test_unknown_model_fails_instead_of_costing_zero() -> None:
    with pytest.raises(pricing.UnknownModelError):
        pricing.cost_usd("claude-made-up", Usage(input_tokens=1))
