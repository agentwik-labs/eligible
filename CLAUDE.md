# CLAUDE.md: instructions for the building agent

You are building **Eligible**, a public portfolio project (see README.md). The owner will show it to hiring managers for AI engineer roles. Optimize for **a working, measured, well-explained system**. Breadth of features matters less.

## Source of truth
- What to build: `SPEC.md`. Order to build it in: `PLAN.md`. How to measure it: `EVALS.md`. Data: `DATA.md`.
- When the docs and your judgment disagree, follow the docs and note the disagreement in `DECISIONS.md` (create it, and add one dated entry per decision).
- Work milestone by milestone. A milestone is done only when its acceptance criteria in PLAN.md pass. Commit at the end of each milestone.

## Hard rules
1. **No employer code or data.** The owner works at a company in the FSA-card space. Do not copy, reference or recreate any code, prompts, schemas, copy or data from an employer. Write everything from scratch, use only public sources (IRS publications) and synthetic data. If a request seems to need employer material, stop and ask.
2. **No real personal or health data.** All receipts are synthetic (DATA.md). Never commit real receipts, names or card numbers.
3. **No secrets in git.** Read keys from `.env` (gitignored) and commit `.env.example` with placeholder values.
4. **Never fake eval numbers.** Every number in the README must come from a committed eval run (`evals/reports/`). If a metric misses its threshold, report the miss. Don't tune the dataset to pass.
5. **Never make up citations.** Every eligibility verdict cites a chunk that was actually retrieved, by ID. A verdict with no supporting chunk becomes `needs_review`.
6. **Keep LLM calls behind one interface** (`llm/client.py`) so models can be swapped and their cost tracked.

## Stack (do not substitute without a DECISIONS.md entry)
- Python 3.12, **uv** for deps, **FastAPI**, **Pydantic v2**, **pytest**, **ruff**, **mypy --strict** on `src/`.
- LLM: Anthropic Claude via the official `anthropic` SDK. Before writing LLM code, load the `claude-api` skill (if available) for current model IDs, structured outputs, tool use and prompt caching.
  - Extraction and verdicts: `claude-sonnet-5-5`. LLM-as-judge and cheap steps: `claude-haiku-5-5`. Make both configurable through env.
- Retrieval: **SQLite + sqlite-vec** for vectors and SQLite **FTS5** for BM25. Hybrid search combines them with reciprocal rank fusion, and a reranker runs on top (SPEC.md §4). No hosted vector DB.
- Embeddings: a local `sentence-transformers` model (`BAAI/bge-small-en-v1.5`), so tests run without network for embeddings.
- Tracing: **Langfuse** (self-host via docker-compose, or cloud if `LANGFUSE_*` env vars are set). Tracing must be optional, and the app must run without it.
- MCP: the official `mcp` Python SDK.
- Frontend: one minimal page (`web/index.html`, plain HTML + JS served by FastAPI). Do not build a SPA.
- CI: GitHub Actions.

## Commands (keep these working and listed in the README)
```
uv sync
uv run pytest                      # unit tests, no network
uv run python -m evals.run --suite smoke   # ~10 cases, used in CI
uv run python -m evals.run --suite full    # all cases, writes evals/reports/<date>.md
uv run uvicorn eligible.api:app --reload
uv run python -m eligible.mcp_server
uv run python -m data.generate     # regenerate synthetic receipts
uv run python -m retrieve.ingest   # build the knowledge index
```

## Testing
- Unit tests must not call the LLM API. Use recorded fixtures (`tests/fixtures/llm/*.json`) behind the `llm/client.py` interface.
- Evals do call the API. They are the integration test.
- Coverage target is 80% on `src/eligible/`, but meaningful tests matter more than the number.

## Code style
- Small modules, typed functions, Pydantic models at every boundary.
- Prompts live in `src/eligible/prompts/*.md` with a version header, and every eval report records the prompt versions it ran.
- No LangChain or LlamaIndex. Writing the retrieval and agent code directly is part of what this project shows.

## Stop and ask the owner before
- Spending more than **$10** in API calls on any single eval run (the estimated cost prints before a full run).
- Creating any public repo, deploying anything, or posting anywhere.
- Adding a paid service or account.
- Changing a threshold in EVALS.md.

## Definition of done (whole project)
All PLAN.md milestones pass. `evals/reports/latest.md` exists and the README's results table is copied from it. The demo runs with `docker compose up`. A 60-second demo script is in `docs/demo-script.md`. `docs/writeup.md` explains what failed and how the evals caught it.
