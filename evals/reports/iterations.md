# M5 iterations

Each change was committed, then measured on the full suite (60 receipts, 441 items).
Labels were never edited. Cost is API-equivalent per receipt for an uncached run.
Failure analysis that drove these changes: `failures-2026-10-28.md`.

| # | Change | Commit | Accuracy | `needs_review` rate | Over-approvals | Invented citations caught | Prompt tokens from cache | Decide cost | Total cost |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Baseline (M4) | `38aceee` | 92.7% | 12.2% | 0 / 130 | 28 | 15.5% | $0.0353 | $0.0500 |
| 1 | Resolve citation IDs written without the chunk suffix | `aaaf405` | 93.9% | 11.1% | 0 / 130 | 15 | 15.5% | $0.0353 | $0.0500 |
| 2 | Eligibility list as a cached knowledge preamble (decide v2) | `09dd063` | 97.5% | 7.5% | 0 / 130 | 10 | 66.6% | $0.0338 | $0.0484 |
| 3 | Trim IRS chunks to the sentences about the items | `45300dd` | 97.5% | 7.5% | 0 / 130 | 4 | 79.7% | $0.0226 | $0.0373 |
| 4 | Haiku 5.5 reads receipts, Sonnet 5.5 still decides | `45300dd` + env | 97.7% | 7.5% | 0 / 130 | 6 | 75.1% | $0.0234 | $0.0245 |
| final | Same configuration, clean uncached run (`latest.md`) | `946ee9f` | 98.2% | 7.0% | 0 / 130 | 5 | 82.9% | $0.0209 | **$0.0218** |

Labels: 5.2% of items are `needs_review`.

## What each change taught

1. **Citation IDs.** 5 of 32 failures came from one receipt where the model cited
   `elist:bandages` instead of `elist:bandages#0`. Strict validation was right to refuse an
   unknown ID, and wrong to treat a known source's short name as unknown. The fix resolves a
   source ID only to a chunk retrieved for that same item, so the no-made-up-citations rule
   holds. Measured at $0: only validation changed, so every model answer replayed from cache.
2. **Knowledge preamble.** 24 of 32 failures were the model saying "the sources don't settle
   it" because retrieval hadn't surfaced the right rule (milk and the food rule, diclofenac
   gel and topical pain relievers). SPEC §2.5 already asked for a cached knowledge preamble.
   Putting all 154 rules in it fixed most of them, and it made the static prefix long enough
   to cache, so decide got *cheaper* despite 7,700 more tokens.
3. **Trimmed chunks.** With the rules in the cached preamble, full ~225-word IRS chunks were
   mostly uncached repetition. Keeping each chunk's three most relevant sentences cut decide
   cost by 33% with no accuracy change, and fewer invented citations.
4. **Haiku for extraction** (approved by the owner as an M5 experiment). Reading a receipt is
   a transcription task: Haiku kept 100% item recall and amounts, and verdict accuracy held,
   while extraction cost fell 13x ($0.0146 to $0.0011). It's slightly weaker at judging
   merchant type (96.7%) and flagged 22 of 23 unreadable lines instead of 23. The gates hold,
   so it's the default now. Sonnet still makes the decisions.

Iteration 4 ran at the same commit as iteration 3 with `ELIGIBLE_EXTRACT_MODEL` overridden,
so it overwrote iteration 3's report file; iteration 3's numbers above come from that run's
log. The laptop slept during iteration 4, so its latency isn't reported here. The final
report (`latest.md`) is a clean uncached run of the shipped configuration.

**Run-to-run variation.** The shipped configuration scored 97.7% in iteration 4 and 98.2% in
the final run, with no code change in between. The model can't be pinned to temperature 0
on the current API (DECISIONS.md), so differences under about a point between single runs
aren't evidence of improvement. The four iterations above each moved accuracy or cost by far
more than that.
