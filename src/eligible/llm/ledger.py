"""Append-only JSONL log of every LLM call, and the cost/token summary built from it."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

from eligible.llm import pricing
from eligible.llm.types import LLMResponse


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, response: LLMResponse) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(response.model_dump_json() + "\n")

    def read(self) -> list[LLMResponse]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()
        return [LLMResponse.model_validate_json(line) for line in lines if line.strip()]


class PromptStats(BaseModel):
    prompt: str  # name@version
    model: str
    calls: int
    cost_usd: Decimal
    mean_cost_usd: Decimal
    mean_prompt_tokens: float
    mean_output_tokens: float
    prompt_cache_read_share: float
    system_variants: int  # >1 means the "static" prefix changed between calls: cache busting


class Summary(BaseModel):
    calls: int
    api_calls: int
    local_cache_hits: int
    cost_usd: Decimal
    avoided_by_local_cache_usd: Decimal
    saved_by_prompt_cache_usd: Decimal
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int
    prompt_cache_read_share: float
    latency_mean_ms: float
    latency_p95_ms: float
    by_prompt: list[PromptStats]


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]


def _share(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def summarize(responses: Iterable[LLMResponse]) -> Summary:
    rows = list(responses)
    api = [r for r in rows if r.source == "api"]
    latencies = [r.latency_ms for r in api]
    groups: dict[tuple[str, str], list[LLMResponse]] = defaultdict(list)
    for r in api:
        groups[(f"{r.prompt_name}@{r.prompt_version}", r.model)].append(r)

    by_prompt = []
    for (prompt, model), items in sorted(groups.items()):
        cost = sum((r.cost_usd for r in items), Decimal(0))
        prompt_tokens = sum(r.usage.prompt_tokens for r in items)
        by_prompt.append(
            PromptStats(
                prompt=prompt,
                model=model,
                calls=len(items),
                cost_usd=cost,
                mean_cost_usd=cost / len(items),
                mean_prompt_tokens=prompt_tokens / len(items),
                mean_output_tokens=sum(r.usage.output_tokens for r in items) / len(items),
                prompt_cache_read_share=_share(
                    sum(r.usage.cache_read_tokens for r in items), prompt_tokens
                ),
                system_variants=len({r.system_hash for r in items}),
            )
        )

    prompt_tokens = sum(r.usage.prompt_tokens for r in api)
    return Summary(
        calls=len(rows),
        api_calls=len(api),
        local_cache_hits=len(rows) - len(api),
        cost_usd=sum((r.cost_usd for r in rows), Decimal(0)),
        avoided_by_local_cache_usd=sum((r.avoided_cost_usd for r in rows), Decimal(0)),
        saved_by_prompt_cache_usd=sum(
            (pricing.uncached_cost_usd(r.model, r.usage) - r.cost_usd for r in api), Decimal(0)
        ),
        prompt_tokens=prompt_tokens,
        output_tokens=sum(r.usage.output_tokens for r in api),
        thinking_tokens=sum(r.usage.thinking_tokens for r in api),
        prompt_cache_read_share=_share(sum(r.usage.cache_read_tokens for r in api), prompt_tokens),
        latency_mean_ms=sum(latencies) / len(latencies) if latencies else 0.0,
        latency_p95_ms=p95(latencies),
        by_prompt=by_prompt,
    )


def render_markdown(summary: Summary) -> str:
    s = summary
    lines = [
        "| Metric | Value |",
        "|---|---|",
        f"| Calls (API / local cache) | {s.calls} ({s.api_calls} / {s.local_cache_hits}) |",
        f"| Spend | ${s.cost_usd:.4f} |",
        f"| Saved by prompt caching | ${s.saved_by_prompt_cache_usd:.4f} |",
        f"| Avoided by local response cache | ${s.avoided_by_local_cache_usd:.4f} |",
        f"| Prompt tokens served from cache | {s.prompt_cache_read_share:.0%} |",
        f"| Thinking share of output tokens | {_share(s.thinking_tokens, s.output_tokens):.0%} |",
        f"| Latency mean / p95 | {s.latency_mean_ms:.0f} ms / {s.latency_p95_ms:.0f} ms |",
        "",
        "| Prompt | Model | Calls | Mean cost | Mean in / out tokens | Cache read | Prefixes |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in s.by_prompt:
        flag = " ⚠" if p.system_variants > 1 else ""
        lines.append(
            f"| {p.prompt} | {p.model} | {p.calls} | ${p.mean_cost_usd:.5f} | "
            f"{p.mean_prompt_tokens:.0f} / {p.mean_output_tokens:.0f} | "
            f"{p.prompt_cache_read_share:.0%} | {p.system_variants}{flag} |"
        )
    return "\n".join(lines)
