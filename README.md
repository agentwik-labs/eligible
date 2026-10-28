# Eligible: FSA/HSA receipt eligibility checker

Upload a receipt. Get back each line item, whether an FSA/HSA can pay for it, **why**, and the IRS source for that answer. A public eval report shows how often the system is right.

This is a portfolio project. It exists to show, in one repo, the skills AI engineer job postings ask for:

| Skill hiring managers screen for | Where it lives in this repo |
|---|---|
| LLM structured extraction | `extract/`: receipt image → typed line items with confidence |
| RAG with citations | `retrieve/`: hybrid search + rerank over IRS Pub 502 and eligibility lists |
| Evals and regression gates | `evals/`: golden set, metrics, LLM-as-judge, CI fails on regression |
| Tool calling / agents / MCP | `mcp_server/`: the checker exposed as MCP tools |
| Guardrails | Personal-data redaction, "needs human review" when the system isn't confident, no made-up citations |
| Observability and cost | Tracing for every request, plus token cost and latency in the eval report |
| Python backend | FastAPI, Pydantic, pytest, uv |

## Status
M0 (skeleton and the metered LLM client) is done. See [PROGRESS.md](PROGRESS.md). There are no
eval results yet, and this README will show only numbers copied from a committed eval report.

## Quickstart
```
uv sync
cp .env.example .env               # add ANTHROPIC_API_KEY
uv run pytest                      # unit tests, no network
uv run uvicorn eligible.api:app --reload
uv run python -m eligible.llm.report       # spend, cache savings and latency from the call ledger
uv run python -m eligible.llm.projection   # projected cost per receipt by model
```
These arrive with their milestones: `python -m data.generate` (M1), `python -m retrieve.ingest`
(M3), `python -m evals.run --suite smoke|full` (M2–M4), `python -m eligible.mcp_server` (M6).

## Cost and token efficiency
Every LLM call goes through one metered client (`src/eligible/llm/`):
- **Exact cost per call.** A Decimal price table covers cache writes (1.25x/2x), cache reads
  and long-context tiers. An unknown model fails instead of costing $0.
- **Prompt caching by construction.** Static instructions are the cached prefix and per-request
  content comes after it. The ledger flags any prompt version whose prefix drifted.
- **Free reruns.** Responses are cached by (model, prompt version, input hash), so unchanged
  eval cases cost nothing. Truncated or refused outputs are never cached and never parsed.
- **Hard spend ceiling.** A worst-case pre-flight estimate stops a run *before* the call that
  could cross the budget.
- **Thinking tokens tracked separately** so effort can be tuned against accuracy.

[docs/cost-model.md](docs/cost-model.md) has the cost projection made before the first prompt,
and what it changed about the plan.

## Docs (read in this order)
1. [CLAUDE.md](CLAUDE.md): rules for the AI agent building this
2. [SPEC.md](SPEC.md): what the system does, its schemas, API and architecture
3. [PLAN.md](PLAN.md): milestones with acceptance criteria. Build in this order
4. [EVALS.md](EVALS.md): metrics, thresholds and the CI gate
5. [DATA.md](DATA.md): synthetic receipts, ground truth and knowledge sources

## Not medical, tax or legal advice
Results are informational. The real decision belongs to the plan administrator.
