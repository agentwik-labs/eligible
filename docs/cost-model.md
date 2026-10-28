# Cost model (projection)

**These are projections, not measurements.** They come from token assumptions in
`src/eligible/llm/projection.py`, written before any prompt exists. The eval report (M4) replaces
them with measured cost per receipt from the call ledger, and the write-up explains any gap.
README numbers only ever come from eval reports.

Regenerate: `uv run python -m eligible.llm.projection`

## Projected cost per receipt (2 LLM calls: extract, decide)

| Model | Extract | Decide | Per receipt | Per 1,000 receipts |
|---|---|---|---|---|
| `claude-opus-5-5` | $0.0250 | $0.0455 | $0.0705 | $70.50 |
| `claude-sonnet-5-5` | $0.0125 | $0.0230 | $0.0355 | $35.50 |
| `claude-haiku-5-5` | $0.0006 | $0.0012 | $0.0018 | $1.78 |

Prices: `src/eligible/llm/pricing.py` (as of 2026-10-06). Assumptions: 7.5 items per receipt,
1,600 image tokens, 5 retrieved chunks of 300 tokens per item with 40% overlap across items,
a 2,500-token static decide prompt read from the prompt cache, and 300 thinking tokens per
call at `effort=low`.

## What this says before writing a single prompt

1. **On the specified model (Sonnet 5.5), the EVALS.md aim of < $0.01 per receipt is missed by
   about 3.5x.** The aim is a target, not a gate, so the spec stands; the miss will be measured
   and reported.
2. **Retrieved chunks dominate the decide call** (~6.7K of ~9K prompt tokens). The cheapest
   levers are, in order: dedupe chunks across items before the call (free), send 3 chunks
   instead of 5 when the reranker score gap is large (measure recall@3 in M3), and trim chunks
   to the matched span.
3. **Output tokens cost 5x input tokens**, and thinking tokens are output. Effort is pinned to
   `low` and the ledger records thinking tokens separately, so an effort sweep in M5 can show
   its accuracy-vs-cost curve.
4. **Haiku 5.5 is ~20x cheaper.** M5 should try Haiku for extraction (a reading task) while
   keeping Sonnet for verdicts, and keep the swap only if the item-recall and verdict-accuracy
   gates still pass. The model is one env var (`ELIGIBLE_EXTRACT_MODEL`).

## How cost is tracked in code

| Mechanism | Where | What it buys |
|---|---|---|
| One LLM interface | `llm/client.py` | Every call is priced, timed and logged; models swap by env var |
| Decimal price table with cache-write (1.25x / 2x) and cache-read rates, long-context tier | `llm/pricing.py` | Cost is exact per call; unknown models fail instead of costing $0 |
| Prompt caching on the static system prompt | `build_params` | Volatile content stays after the breakpoint so the prefix is reusable |
| Cache-bust detector | `ledger.py` (`Prefixes` column) | Flags a prompt version whose "static" prefix changed between calls |
| Response cache keyed by (model, prompt version, input hash) | `ReplayClient` | Re-running unchanged eval cases costs $0; truncated or refused answers are never cached |
| Worst-case pre-flight budget | `llm/budget.py` | A run stops before the call that could cross `ELIGIBLE_BUDGET_USD` (default $10, CLAUDE.md) |
| Call ledger + report | `logs/llm_calls.jsonl`, `python -m eligible.llm.report` | Spend, savings from both caches, thinking share, p95 latency, per prompt |
