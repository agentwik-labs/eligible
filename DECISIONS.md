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
