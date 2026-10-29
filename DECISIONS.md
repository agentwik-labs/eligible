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

## 2026-10-28: Own public repo
M0 was built in a subfolder of the owner's working repo. The owner then approved a public repo,
so the folder was split out with its history to `agentwik-labs/eligible`.

## 2026-10-28: Haiku for extraction is an M5 experiment, not a spec change
The cost projection (docs/cost-model.md) misses the < $0.01 aim on Sonnet 5.5. The owner
approved trying Haiku 5.5 for extraction in M5. It is kept only if item recall and verdict
accuracy still meet their EVALS.md gates. Until then, the stack stays as specified.

## 2026-10-28: Later-milestone files are created with their milestone
SPEC §7 lists `Dockerfile`, `docker-compose.yml`, `evals.yml` and modules like `decide.py`.
M0 creates the directories and packages; each file is added in the milestone that fills it,
so the repo never contains empty stubs that look finished.

## 2026-10-28: The question is HSA/FSA reimbursement, not the tax deduction
Pub 502 is written for the itemized deduction and says non-prescribed drugs aren't includible.
For HSAs and FSAs, CARES Act §3702 removed that limit for expenses after 2019, and Pub 969
says so in plain words for FSAs and HRAs. The list follows the HSA/FSA rule and cites both,
and the Pub 502 rule stays in the index as a deliberate retrieval trap.

## 2026-10-28: CARES Act text from govinfo.gov
DATA.md says to cite congress.gov, which returned 403 to automated download. govinfo.gov
serves the same enrolled public law (Pub. L. 116-136). Only §3702 is indexed.

## 2026-10-28: Vitamins are dual_purpose, as DATA.md says, though the source reads stricter
Pub 502 allows supplements only when "recommended by a medical practitioner as treatment for
a specific medical condition diagnosed by a physician", which is close to the
`needs_prescription` definition. DATA.md §4 lists vitamins as dual purpose, so the list
follows the docs. Worth revisiting if the evals show the model splitting these two classes.

## 2026-10-28: Golden schema extensions
DATA.md §2 shows the minimal label. The golden files add `raw_text` (to match extracted items
to labels), `quantity`, `unit_price`, `subtotal_printed`, `tax`, `pii` (what the redaction
eval must catch) and `seed`. Each list entry also carries `merchants` and `products`
(receipt text, normalized name, price), which the generator needs.

## 2026-10-28: Verdict mix enforced with a quota, not per-item sampling
Sampling each item's verdict independently gave 4% `needs_prescription` (target 10%):
pharmacies are 40% of receipts and sell few such items. The generator assigns verdicts
across all item slots, weighted by what's still needed among what each merchant sells. The
mix is within 1 point of DATA.md §2 on every class.

## 2026-10-28: Bundled DejaVu Sans Mono
Receipt PNGs use a committed copy of DejaVu Sans Mono (free license in `data/fonts/`), so
images render the same on every machine and in CI.

## 2026-10-28: Claude Code CLI as a second LLM backend
There is no API key yet, and the owner said to use Claude for now. `llm/claude_code.py` is a
second `LLMClient` implementation that runs `claude -p` on the signed-in Claude login: our
system prompt replaces Claude Code's, all tools and MCP servers are off, and it runs in an
empty directory. It reports the same usage fields as the API, and on a measured call its own
`costUSD` matched `llm/pricing.py` to within $0.0000002. `ELIGIBLE_LLM_BACKEND=auto` picks
the API when `ANTHROPIC_API_KEY` is set. CLAUDE.md names the `anthropic` SDK, which stays the
production backend; the CLI is a stand-in. Costs in reports are API-equivalent.

Side effects: the CLI writes its prompt cache with the 1-hour TTL (2x input price instead of
1.25x), and it can't send images, so extraction runs on receipt text for now.

## 2026-10-28: Extraction is measured on receipt text until images can be sent
SPEC §1 accepts receipt text or an image. The Claude Code backend sends text only, so the M2
eval reads `data/receipts/*.txt`. Image extraction (and the noisy/rotated adversarial set)
gets measured once the API backend is available. Text extraction is the easier task, and the
M2 numbers should be read that way.

## 2026-10-28: Smoke suite composition
`evals/suites/smoke.json` holds 10 receipts chosen in code to cover every verdict, a totals
mismatch, a card number and a patient name. It has 73 items. CI runs it.

## 2026-10-28: Citation expansion in retrieval
The first ablation missed recall@5 badly (about 50%), and the HSA/FSA rule for OTC items was
almost never retrieved (0-2%). The cause: receipt words ("ibuprofen") never appear in IRS
prose ("over-the-counter medicine"), so neither BM25 nor vectors connect them. The list
entries do, because each one names products and cites the governing sections. After ranking,
the retriever now inserts the sections a retrieved list entry cites, choosing each section's
chunk that best matches the entry's rule. The ablation keeps every earlier configuration so
the before and after are both on record.

## 2026-10-28: Retrieval runs hybrid without the reranker by default
In the ablation the cross-encoder lowered recall@5 (52.8% to 49.2%) and adds ~1.6 s per
item on CPU, about 13 s per receipt. `ELIGIBLE_RETRIEVAL_MODE=rerank` turns it back on.

## 2026-10-28: A thin UI slice before M5
The owner asked to see a working version. The demo page, `/v1/check`, `/v1/sources/{id}`
and sample endpoints (part of M6) were built right after the M4 pipeline, ahead of M5
tuning. M6's MCP server and the recorded transcript still come after M5.

## 2026-10-28: The decide prompt states the HSA/FSA rule for OTC medicine
The system prompt says outright that Pub 502's non-prescription exclusion is a deduction rule
and that OTC medicine is covered for HSAs and FSAs. That's domain knowledge the product
should carry, but it means the decide step isn't tested on discovering the trap from sources
alone. The retrieval ablation's "OTC rule found" column measures that part.

## 2026-10-28: Rules in the preamble count as provided sources
With the eligibility list in the cached decide prompt (M5 iteration 2), every list entry is in
the model's context, so citing one is citing a provided source. CLAUDE.md rule 5 still holds:
validation accepts a citation only if it names a retrieved chunk or a list entry, and the IRS
sections behind a cited entry are attached from the index by ID, never generated.

## 2026-10-28: The adversarial suite is text-only for now
EVALS.md §1 lists blurry receipts. The Claude Code backend can't send images, so the 15
adversarial cases are text damage: prompt injection (5), OCR-style noise (5) and structural
changes (5). Image degradation (`render_png(..., degrade=...)` exists) gets measured once
the API backend is available.

## 2026-10-28: Haiku 5.5 reads receipts by default
CLAUDE.md specifies Sonnet for extraction. The owner approved trying Haiku there in M5, kept
only if the gates hold (see the Haiku entry above). In iteration 4 it kept 100% item recall
and amounts, verdict accuracy went from 97.5% to 97.7%, and extraction cost fell 13x, so
`ELIGIBLE_EXTRACT_MODEL` now defaults to `claude-haiku-5-5`. Sonnet still makes the verdicts.

## 2026-10-29: Docker on Colima, CPU-only PyTorch in the image
Docker was installed as Colima (MIT-licensed, a Linux VM on macOS virtualization) with the
Docker CLI and Compose plugin, all in `~/.local`, with no admin rights or Docker Desktop.
The first image was 20.4 GB because Linux PyTorch wheels pull in the CUDA stack; retrieval
only runs small models on CPU, so Linux installs now use PyTorch's CPU-only index
(`[tool.uv.sources]`). With the uv download cache and local tool caches kept out of the
image, it's 2.45 GB and rebuilds in about 2.5 minutes. `ANTHROPIC_API_KEY` is optional for
the container: without it, every page works and receipts already in the response cache
replay; a new receipt gets a 503 that says why.
