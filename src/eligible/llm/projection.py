"""Back-of-envelope cost per receipt, before any code calls the API.

These are *projections* from token assumptions, not measurements. The eval report
(M4+) replaces them with measured numbers; the assumptions are listed so the gap
between projected and measured can be explained.

    uv run python -m eligible.llm.projection
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from eligible.llm import pricing
from eligible.llm.types import Usage


class Scenario(BaseModel):
    items_per_receipt: float = 7.5  # DATA.md: 3-12 items
    image_tokens: int = 1_600
    extract_instructions_tokens: int = 900
    extract_output_tokens_per_item: int = 60
    decide_static_tokens: int = 2_500  # system prompt + knowledge preamble, prompt-cached
    chunks_per_item: int = 5
    tokens_per_chunk: int = 300
    chunk_dedup: float = 0.4  # share of chunks repeated across items on one receipt
    decide_output_tokens_per_item: int = 80
    thinking_tokens_per_call: int = 300  # at effort=low; measure in M4


class StageCost(BaseModel):
    stage: str
    usage: Usage
    cost_usd: Decimal


def stages(s: Scenario, model: str) -> list[StageCost]:
    extract = Usage(
        input_tokens=s.image_tokens + s.extract_instructions_tokens,
        output_tokens=round(s.items_per_receipt * s.extract_output_tokens_per_item)
        + s.thinking_tokens_per_call,
        thinking_tokens=s.thinking_tokens_per_call,
    )
    chunk_tokens = s.items_per_receipt * s.chunks_per_item * s.tokens_per_chunk
    decide = Usage(
        input_tokens=round(chunk_tokens * (1 - s.chunk_dedup)),
        cache_read_tokens=s.decide_static_tokens,  # warm cache: back-to-back receipts
        output_tokens=round(s.items_per_receipt * s.decide_output_tokens_per_item)
        + s.thinking_tokens_per_call,
        thinking_tokens=s.thinking_tokens_per_call,
    )
    return [
        StageCost(stage=name, usage=u, cost_usd=pricing.cost_usd(model, u))
        for name, u in (("extract", extract), ("decide", decide))
    ]


def render(s: Scenario) -> str:
    lines = [
        "| Model | Extract | Decide | Per receipt | Per 1,000 receipts |",
        "|---|---|---|---|---|",
    ]
    for model in pricing.PRICES:
        costs = stages(s, model)
        total = sum((c.cost_usd for c in costs), Decimal(0))
        lines.append(
            f"| `{model}` | ${costs[0].cost_usd:.4f} | ${costs[1].cost_usd:.4f} | "
            f"${total:.4f} | ${total * 1000:.2f} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(render(Scenario()))
