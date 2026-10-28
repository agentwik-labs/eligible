"""Offline demo of the metered LLM layer: `uv run python -m eligible.demo`.

No API calls. A simulated model returns token counts shaped like the cost projection, so
everything around it is real: pricing, the response cache, the budget guard, the ledger
and its report.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from eligible.config import get_settings
from eligible.llm import pricing
from eligible.llm.budget import Budget, BudgetExceededError, estimate_max_cost_usd
from eligible.llm.client import MeteredClient, ReplayClient
from eligible.llm.ledger import Ledger, render_markdown, summarize
from eligible.llm.types import LLMRequest, LLMResponse, Message, Usage

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden"
DECIDE_SYSTEM = "You decide FSA/HSA eligibility from the cited IRS sections only. " * 120


class SimulatedModel:
    """Stands in for the API. Behaves like prompt caching does: the first call with a
    given system prompt writes the cache, later calls read it."""

    def __init__(self) -> None:
        self._seen_prefixes: set[str] = set()

    def complete(self, request: LLMRequest) -> LLMResponse:
        static = len(request.system) // 4
        dynamic = sum(len(str(m.content)) for m in request.messages) // 4 + 900
        prefix = request.system_hash()
        cached = prefix in self._seen_prefixes
        self._seen_prefixes.add(prefix)
        usage = Usage(
            input_tokens=dynamic,
            output_tokens=520,
            thinking_tokens=300,
            cache_read_tokens=static if cached else 0,
            cache_write_5m_tokens=0 if cached else static,
        )
        return LLMResponse(
            request_key=request.cache_key(),
            prompt_name=request.prompt_name,
            prompt_version=request.prompt_version,
            system_hash=prefix,
            model=request.model,
            text=json.dumps({"verdicts": "simulated"}),
            stop_reason="end_turn",
            usage=usage,
            cost_usd=pricing.cost_usd(request.model, usage),
            latency_ms=1800.0 + (dynamic % 700),
            effort=request.effort,
        )


def decide_request(receipt: dict[str, object], system: str, version: str) -> LLMRequest:
    return LLMRequest(
        model=get_settings().decide_model,
        prompt_name="decide",
        prompt_version=version,
        system=system,
        messages=[Message(role="user", content=json.dumps(receipt["items"]))],
        max_tokens=2048,
        effort="low",
    )


def heading(text: str) -> None:
    print(f"\n\033[1m{text}\033[0m")


def main() -> None:
    receipts = [json.loads(p.read_text()) for p in sorted(GOLDEN.glob("r*.json"))[:10]]
    work = Path(tempfile.mkdtemp(prefix="eligible-demo-"))
    model = SimulatedModel()
    ledger = Ledger(work / "calls.jsonl")

    heading("1. Pre-flight budget: a run stops before the call that could cross the limit")
    tight = MeteredClient(ReplayClient(work / "cache-a", inner=model), Budget(Decimal("0.05")))
    done = 0
    try:
        for r in receipts:
            tight.complete(decide_request(r, DECIDE_SYSTEM, "1"))
            done += 1
    except BudgetExceededError as e:
        print(f"   stopped after {done} receipts: {e}")
    worst = estimate_max_cost_usd(decide_request(receipts[0], DECIDE_SYSTEM, "1"))
    print(f"   worst case per call is ${worst:.4f} (no cache, every allowed output token)")

    heading("2. First eval run: 10 receipts, static prompt cached after the first call")
    client = MeteredClient(ReplayClient(work / "cache", inner=model), Budget(Decimal(10)), ledger)
    for r in receipts:
        client.complete(decide_request(r, DECIDE_SYSTEM, "1"))
    print(f"   spent ${client.budget.spent_usd:.4f}")

    heading("3. Rerun with nothing changed: answers replay from the response cache")
    before = client.budget.spent_usd
    for r in receipts:
        client.complete(decide_request(r, DECIDE_SYSTEM, "1"))
    print(f"   spent ${client.budget.spent_usd - before:.4f} on the rerun")

    heading("4. A bug: a timestamp in the system prompt busts the prompt cache every call")
    for r in receipts[:4]:
        busted = DECIDE_SYSTEM + f" Today is {datetime.now().isoformat()}."
        client.complete(decide_request(r, busted, "2-bug"))

    heading("5. Ledger report (python -m eligible.llm.report)")
    print(render_markdown(summarize(ledger.read())))
    print(
        "\n   decide@2-bug shows a prefix count above 1 (⚠) and 0% cache read: the report flags it."
        "\n   Token counts are simulated. The pricing, caching, budget and ledger code is real."
    )


if __name__ == "__main__":
    main()
