"""Spend ceiling. A run stops before the call that could cross it, not after."""

from __future__ import annotations

import math
from decimal import Decimal

from eligible.llm import pricing
from eligible.llm.types import LLMRequest

CHARS_PER_TOKEN = 3.5  # conservative for English; overestimates tokens, which is the safe side
IMAGE_TOKENS = 1_600  # a tall receipt photo, resized by the API to ~1.15 MP


class BudgetExceededError(RuntimeError):
    pass


def estimate_input_tokens(request: LLMRequest) -> int:
    chars = len(request.system)
    images = 0
    for message in request.messages:
        if isinstance(message.content, str):
            chars += len(message.content)
            continue
        for block in message.content:
            if block.get("type") == "image":
                images += 1
            else:
                chars += len(str(block.get("text", "")))
    return math.ceil(chars / CHARS_PER_TOKEN) + images * IMAGE_TOKENS


def estimate_max_cost_usd(request: LLMRequest) -> Decimal:
    """Worst case: nothing cached, every allowed output token used."""
    input_tokens = estimate_input_tokens(request)
    p = pricing.price_for(request.model).for_prompt(input_tokens)
    return (input_tokens * p.input + request.max_tokens * p.output) / pricing.MTOK


class Budget:
    def __init__(self, limit_usd: Decimal) -> None:
        self.limit_usd = limit_usd
        self.spent_usd = Decimal(0)

    @property
    def remaining_usd(self) -> Decimal:
        return self.limit_usd - self.spent_usd

    def check(self, worst_case_usd: Decimal) -> None:
        if worst_case_usd > self.remaining_usd:
            raise BudgetExceededError(
                f"next call could cost ${worst_case_usd:.4f}; only ${self.remaining_usd:.4f} "
                f"of the ${self.limit_usd} budget is left"
            )

    def charge(self, cost_usd: Decimal) -> None:
        self.spent_usd += cost_usd
