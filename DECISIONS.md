# DECISIONS.md

One dated entry per decision, especially where the docs and the build disagree.

## 2026-10-28: No `temperature=0`
EVALS.md §5 asks for temperature 0 "where the API allows it". API version 2026-10-21, used by the
installed SDK (`anthropic` 2.3.0), rejects `temperature`/`top_p`/`top_k` on every model, so the
client sends none. Reproducibility comes from pinned model IDs, prompt versions in every
request hash, and the response cache: a rerun of an unchanged case replays the recorded answer.

## 2026-10-28: Effort pinned to `low` by default
Sonnet 5.5 defaults to `high`, and thinking tokens are billed as output. The projection
(docs/cost-model.md) already misses the cost aim, so the default is `low` and configurable
(`ELIGIBLE_EFFORT`). M5 sweeps it against verdict accuracy.

## 2026-10-28: No server-side refusal fallback
The Claude API skill recommends `fallbacks: "default"` for Sonnet 5.5. It's left off: a fallback
silently bills a different model, which breaks per-model cost attribution and the eval's pinned
model IDs. A refusal is returned with `stop_reason="refusal"`, never parsed
(`IncompleteResponseError`), and still counted in the ledger. M4 turns it into `needs_review`.

## 2026-10-28: Haiku 5.5 cache-read rate assumed
The cached price table lists Haiku 5.5 input/output ($0.10 / $0.50) but not its cache-read
rate. `pricing.py` assumes the standard 0.1x ($0.01/MTok). Verify against the pricing page
before the first full eval run.

## 2026-10-28: Project lives in `fsa-checker/` for now
It is built inside the owner's working repo until the owner approves creating its public repo
(CLAUDE.md: stop and ask). `.github/workflows/ci.yml` is written for the project's own repo
root, so CI runs once the folder becomes its own repo; until then the same commands are run
locally.

## 2026-10-28: Later-milestone files are created with their milestone
SPEC §7 lists `Dockerfile`, `docker-compose.yml`, `evals.yml` and modules like `decide.py`.
M0 creates the directories and packages; each file is added in the milestone that fills it,
so the repo never contains empty stubs that look finished.
