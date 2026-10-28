"""Price table and cost math. Costs are Decimal: summing thousands of float cents drifts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from eligible.llm.types import TokenBreakdown, Usage

PRICES_AS_OF = "2026-10-06"
PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"

MTOK = Decimal(1_000_000)
CACHE_WRITE_5M = Decimal("1.25")  # multiplier on the base input rate
CACHE_WRITE_1H = Decimal("2")


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: Decimal
    output: Decimal
    cache_read: Decimal
    # Some models bill the whole request at a higher rate once the prompt passes a size.
    long_context_threshold: int | None = None
    long_input: Decimal | None = None
    long_output: Decimal | None = None

    def for_prompt(self, prompt_tokens: int) -> Price:
        if self.long_context_threshold is None or prompt_tokens <= self.long_context_threshold:
            return self
        if self.long_input is None or self.long_output is None:
            raise ValueError("long_context_threshold set without long-context rates")
        ratio = self.cache_read / self.input
        return Price(self.long_input, self.long_output, self.long_input * ratio)


def _d(value: str) -> Decimal:
    return Decimal(value)


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(_d("4.00"), _d("20.00"), _d("0.20")),
    "claude-sonnet-5-5": Price(_d("2.00"), _d("10.00"), _d("0.20")),
    "claude-haiku-5-5": Price(
        _d("0.10"),
        _d("0.50"),
        _d("0.01"),
        long_context_threshold=100_000,
        long_input=_d("0.50"),
        long_output=_d("2.50"),
    ),
}


class UnknownModelError(KeyError):
    """Raised instead of silently costing an unknown model at $0."""


def price_for(model: str) -> Price:
    try:
        return PRICES[model]
    except KeyError:
        raise UnknownModelError(f"no price for {model!r}; add it to llm/pricing.py") from None


def breakdown(model: str, usage: Usage) -> TokenBreakdown:
    p = price_for(model).for_prompt(usage.prompt_tokens)
    write = usage.cache_write_5m_tokens * CACHE_WRITE_5M + usage.cache_write_1h_tokens * (
        CACHE_WRITE_1H
    )
    return TokenBreakdown(
        input=usage.input_tokens * p.input / MTOK,
        output=usage.output_tokens * p.output / MTOK,
        cache_read=usage.cache_read_tokens * p.cache_read / MTOK,
        cache_write=write * p.input / MTOK,
    )


def cost_usd(model: str, usage: Usage) -> Decimal:
    return breakdown(model, usage).total


def uncached_cost_usd(model: str, usage: Usage) -> Decimal:
    """What the same call would have cost with prompt caching off."""
    p = price_for(model).for_prompt(usage.prompt_tokens)
    return (usage.prompt_tokens * p.input + usage.output_tokens * p.output) / MTOK
