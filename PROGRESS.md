# PROGRESS.md

## M0: Skeleton (2026-10-28)

**Done**
- uv project (Python 3.12), SPEC §7 layout, FastAPI `/healthz`, `.env.example`, ruff, mypy
  `--strict`, pytest with coverage, GitHub Actions CI (lint, format, types, tests).
- `llm/client.py`: `LLMClient` protocol; `AnthropicClient` (real); `ReplayClient` (fixtures in
  tests, read-through response cache in evals); `MeteredClient` (worst-case pre-flight budget
  plus call ledger).
- Cost layer beyond the M0 ask, because cost is a headline metric of this project:
  Decimal pricing with cache-write/read and long-context rates, a ledger report
  (`python -m eligible.llm.report`), and a pre-build cost projection (`docs/cost-model.md`).

**Acceptance**
- `uv run pytest`: 30 passed, 99% coverage on `src/eligible/`. ruff and mypy clean.
- `/healthz` returns 200 (TestClient and a live uvicorn run).
- CI: runs on GitHub Actions at github.com/agentwik-labs/eligible.

**Owner decisions (2026-10-28)**
1. Public repo approved: `agentwik-labs/eligible`.
2. Approved: M5 tries Haiku 5.5 for extraction, kept only if the gates still pass.


## M1: Synthetic data and ground truth (2026-10-28)

**Done**
- Sources: Pub 502 (HTML and PDF), Pub 969, CARES Act §3702 (govinfo.gov) and Notice 2013-71
  in `data/knowledge/raw/`. `SOURCES.md` lists the URL, retrieval date and SHA-256 of each.
- Parsing into 205 citable sections with heading paths (`data/knowledge/sections.jsonl`).
  It handles IRS quirks: list entries at the same heading level as their list title, plus
  "Caution" callouts and worksheet boxes.
- `eligibility_list.yaml`: 154 entries and 273 receipt products. Every entry cites sections,
  and a test checks they exist.
- `data/generate.py`: 60 receipts (text and PNG) with golden labels, seed 20261028. The
  verdict mix is within 1 point of DATA.md §2, the merchant mix is exact, 6 receipts have a
  totals mismatch, and some carry fake personal data for the redaction tests.
- `data/golden/AUDIT.md`: the agent's spot-check of 20 receipts (4 findings, 2 fixed).

**Acceptance**
- 60 receipts with golden JSON validate against `GoldenReceipt`: yes (`tests/test_data.py`).
- Verdict distribution matches DATA.md §2: yes, within 2 points (a test enforces this).
- Every list entry has a source: yes, and every source resolves to a parsed section.
- The dataset regenerates byte-for-byte from its seed (a test enforces this).

**Open**
- The human spot-check (AUDIT.md pass 2) is the owner's.
- The retrieval trap is now in the data: Pub 502 says OTC drugs are excluded, and the
  CARES Act / Pub 969 say they're eligible. M3 retrieval and M4 verdicts will be measured on it.


## M2: Redaction and extraction (2026-10-28)

**Done**
- `redact.py`: Luhn-checked card numbers, phones, emails, and names after "Patient:"/"Name:".
  14 unit tests, plus a test that no personal data in any of the 60 receipts survives.
- `extract/`: one structured-output call per receipt with a strict JSON schema and per-field
  confidence. Prompt in `prompts/extract.md` (version 1). Money stays exact (Decimal).
- `llm/claude_code.py`: Claude Code CLI backend, so evals run without an API key (DECISIONS).
- `evals/run.py`, `evals/metrics.py`: suites, the EVALS.md §2.1 metrics, a pre-run cost
  estimate with the budget check, gates, and the report format from EVALS.md §4.

**Results** (`evals/reports/`, text input, Sonnet 5.5 at effort low, Claude Code backend)
| Metric | Smoke (10) | Full (60) |
|---|---|---|
| Item recall / precision | 100% / 100% | 100% / 100% |
| Amount, quantity, merchant, date, total | 100% | 100% |
| Totals mismatches caught | 1 of 1 | 6 of 6, 0 false alarms |
| Redaction leaks | 0 | 0 |
| Unreadable lines flagged by low confidence | | 23 of 23 (1 of 418 other items) |
| Cost per receipt (uncached) | $0.0142 | $0.0146 |
| Prompt tokens from cache | 67% | 65% |
| Latency p95 | 12.1 s | 11.6 s |

**Read with care**
- Clean synthetic text is easy, so 100% says the pipeline works, not that extraction is
  solved. The harder cases are images and the adversarial set (M5).
- Every amount was reported at 0.95+ confidence and every amount was right, so calibration
  has no spread to judge yet.
- Output is 1,050+ tokens per receipt and about 70% of the cost. The confidence block on every
  field is most of it. That's the first cost lever for M5.
- Cost is already near the projection's $0.0125 for extraction, so the decide step decides
  whether the < $0.01/receipt aim is reachable.


## M3: Retrieval (2026-10-28)

**Done**: section-aware chunking (446 chunks), SQLite FTS5 BM25 plus sqlite-vec vectors
(`bge-small`, local), reciprocal rank fusion, optional `bge-reranker-base` rerank, exact-match
boost, and citation expansion. Ablation in `evals/reports/retrieval-ablation.md`.

**Accept**: hybrid plus rerank alone **missed** the target (recall@5 49.2%), and the report
keeps that row. The cause is that product names never appear in IRS prose. With citation
expansion: recall@5 93.8% (hybrid, 11 ms) and 95.7% (with rerank, 1.6 s), meeting the 90%
target. The reranker stays off by default (DECISIONS.md).

## M4: Decide and validate (2026-10-28)

**Done**: one decision call per receipt with sources sent once, deterministic validation
(citations must be retrieved, low confidence goes to review, totals checked), and the
pipeline, API and demo page (a thin M6 slice, brought forward at the owner's request).

**Results** (`evals/reports/latest.md`, 60 receipts, 441 items): verdict accuracy 92.7%,
0 of 130 over-approvals, 28 invented citations removed and 0 through validation, 0 leaks,
$0.050 per receipt ($0.015 extract, $0.035 decide), p95 9.3 s. All gates pass.

**Open**: the LLM-as-judge for reason quality (EVALS.md §2.4) isn't built yet; it needs 20
human-labelled reasons from the owner to validate the judge. The `needs_review` rate is 12.2%
against 5.2% in the labels: every verdict error is this cautious kind.


## M5: Iterate using evals (2026-10-28)

**Done**: failure analysis (`evals/reports/failures-2026-10-28.md`), four measured changes
(`evals/reports/iterations.md`), and the 15-case adversarial suite.

**Accept**: `iterations.md` shows 4 changes with before/after metrics. Accuracy went from 92.7%
to 98.2%, the review rate from 12.2% to 7.0%, and cost per receipt from $0.050 to $0.0218.
Over-approvals stayed at 0. Adversarial: 0 of 46 verdicts changed by prompt injection.

**Open**: image input and blurred receipts (needs the API backend), the reason-quality judge
(needs 20 owner-labelled reasons), and latency (13 s mean, mostly per-call CLI startup).


## M6: API, demo page, MCP (2026-10-29)

**Done**: `/v1/check`, `/v1/sources/{id}` and the demo page (built after M4), and the MCP
server (`python -m eligible.mcp_server`) with `check_receipt`, `check_item` and
`search_rules`. Each tool call is logged with its latency and model cost.

**Accept**: a sample receipt can be checked in the browser, with clickable citations. The MCP
tools work from Claude Code: `docs/mcp-demo.md` is a recorded session in which Claude called
`check_item` twice in parallel and answered the SPEC question. Measured: client $0.0255 and
13.0 s; tool calls $0.059 (writing the rules preamble to cache) and $0.0086 (reading it).
