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

**Next: M1** synthetic receipts plus golden labels (`data/generate.py`), `eligibility_list.yaml`
(~150 items), and IRS sources downloaded with retrieval dates.
