from decimal import Decimal

from eligible.llm.ledger import p95, render_markdown, summarize
from eligible.llm.types import LLMResponse, Usage


def row(**overrides: object) -> LLMResponse:
    fields: dict[str, object] = {
        "request_key": "k",
        "prompt_name": "decide",
        "prompt_version": "1",
        "system_hash": "aaa",
        "model": "claude-sonnet-5-5",
        "text": "{}",
        "stop_reason": "end_turn",
        "usage": Usage(input_tokens=1_000, cache_read_tokens=3_000, output_tokens=100),
        "cost_usd": Decimal("0.0036"),
        "latency_ms": 1_000.0,
    }
    fields.update(overrides)
    return LLMResponse.model_validate(fields)


def test_p95() -> None:
    assert p95([float(i) for i in range(1, 101)]) == 95.0
    assert p95([]) == 0.0


def test_summary_separates_spend_from_savings() -> None:
    rows = [
        row(),
        row(latency_ms=3_000.0),
        row(source="cache", cost_usd=Decimal(0), avoided_cost_usd=Decimal("0.0036")),
    ]
    s = summarize(rows)
    assert (s.calls, s.api_calls, s.local_cache_hits) == (3, 2, 1)
    assert s.cost_usd == Decimal("0.0072")
    assert s.avoided_by_local_cache_usd == Decimal("0.0036")
    assert s.prompt_cache_read_share == 0.75
    # uncached would be 4000*$2 + 100*$10 = $0.009 per call
    assert s.saved_by_prompt_cache_usd == 2 * (Decimal("0.009") - Decimal("0.0036"))
    assert s.latency_mean_ms == 2_000.0  # cache hits excluded from latency


def test_changing_system_prompt_within_a_version_is_flagged() -> None:
    s = summarize([row(system_hash="aaa"), row(system_hash="bbb")])
    assert s.by_prompt[0].system_variants == 2
    assert "2 ⚠" in render_markdown(s)
