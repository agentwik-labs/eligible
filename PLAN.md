# PLAN.md: milestones

Build in order. Each milestone ends with: all acceptance criteria pass, `uv run pytest` passes, ruff and mypy are clean, a commit, and a short entry in `PROGRESS.md` (what was done, what's next, any open questions).

## M0: Skeleton (≈0.5 day)
- uv project, the layout from SPEC §7, FastAPI `/healthz`, `.env.example`, ruff, mypy, pytest, and a CI workflow running lint and tests.
- `llm/client.py` interface with a real implementation and a fixture-replay implementation.

**Accept:** `uv run pytest` passes in CI, and `/healthz` returns 200.

## M1: Synthetic data and ground truth (≈1.5 days)
- Implement `data/generate.py` per DATA.md: 60 receipts as text, each rendered to PNG, with golden labels.
- Hand-write `data/knowledge/eligibility_list.yaml` (~150 items) with a source reference for each item.
- Download the public IRS sources listed in DATA.md §3 into `data/knowledge/raw/`, keeping URLs and retrieval dates.

**Accept:** 60 receipts plus `data/golden/*.json` validate against the schema. The verdict distribution matches DATA.md §2. Every list entry has a source.

## M2: Extraction (≈2 days)
- Redaction plus structured extraction (SPEC §2.1–2.2).
- First eval: field-level extraction metrics on the golden set (EVALS.md §2.1).

**Accept:** the extraction eval runs and writes a report, and its numbers are recorded in PROGRESS.md even if they're below threshold. All redaction unit tests pass.

## M3: Retrieval (≈2 days)
- Ingestion (chunking with heading paths), BM25, vectors, RRF fusion, reranking, and exact-match boost.
- Retrieval eval: recall@5 and MRR against each golden item's `gold_source_ids`.
- Write up the ablation: BM25 alone, vectors alone, hybrid, and hybrid plus rerank.

**Accept:** the ablation table is in `evals/reports/retrieval-ablation.md`. Hybrid plus rerank meets the EVALS.md threshold, or the miss is explained.

## M4: Decide and validate (≈2 days)
- Decision call with citations and prompt caching, plus deterministic validation (SPEC §2.5–2.6).
- End-to-end eval (EVALS.md §2.3–2.4), including the LLM-as-judge for reason quality.

**Accept:** a full eval report exists, with zero unsupported citations getting through (this is a hard gate) and a cost per receipt reported.

## M5: Iterate using evals (≈2 days, the most important milestone for the write-up)
- Run the full suite and collect the failures in `evals/reports/failures-<date>.md`.
- Make at least **three** targeted improvements (for example: better normalization for abbreviations, a dual-purpose prompt rule, a merchant-type prior). After each one, rerun and record the before/after numbers.
- Never edit golden labels to raise scores unless the label is provably wrong. In that case, log the correction in DECISIONS.md with a source.

**Accept:** `evals/reports/iterations.md` shows at least 3 changes with before/after metrics.

## M6: API, demo page, MCP (≈1.5 days)
- `/v1/check`, `/v1/sources/{id}`, the demo page, and the MCP server with its 3 tools.
- `docs/mcp-demo.md` with a real transcript.

**Accept:** you can upload a sample receipt in the browser and see verdicts with clickable citations. The MCP tools work from Claude Code.

## M7: Observability and CI gate (≈1 day)
- Tracing (SPEC §5).
- `.github/workflows/evals.yml` runs the smoke suite on every PR. It needs the `ANTHROPIC_API_KEY` secret, and skips with a notice if the secret is missing. It fails if any EVALS.md gate fails.

**Accept:** a deliberately broken prompt on a branch fails the eval gate (document this in the write-up).

## M8: Packaging and story (≈1 day)
- `docker compose up` brings up the app (and Langfuse optionally).
- README: a results table copied from `evals/reports/latest.md`, an architecture diagram (Mermaid), quickstart, and the MCP config.
- `docs/writeup.md` (800–1200 words): the problem, the architecture, **what failed and how the evals caught it**, and the cost/latency tradeoffs.
- `docs/demo-script.md`: a 60-second walkthrough.

**Accept:** a fresh clone gets to a working demo in under 5 minutes by following the README.
