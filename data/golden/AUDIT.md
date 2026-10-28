# AUDIT.md: golden label spot-check

DATA.md §2 asks for 20 receipts to be checked by hand. There are two passes, and they are kept
separate so nobody mistakes one for the other.

## Pass 1: build agent (Claude), 2026-10-28

Sample: 20 receipts drawn with `random.Random(502).sample(range(1, 61), 20)`:
r0003 r0005 r0011 r0013 r0016 r0021 r0023 r0024 r0025 r0028
r0033 r0041 r0042 r0045 r0046 r0047 r0048 r0052 r0058 r0060

Checked for each item: the label's verdict equals its list entry's verdict, the entry's rule
matches the cited section text (read from `sections.jsonl` while writing the list), and the
item is plausible for the merchant. Checked for each receipt: totals and the mismatch flag,
and that every personal-data value is fake (Luhn-valid test cards, 555-01xx, example.com).
The tests in `tests/test_data.py` check these automatically for all 60 receipts.

Findings and what changed:
| # | Finding | Action |
|---|---|---|
| 1 | A $1,450 denture appeared on a pharmacy receipt: merchants were set per entry, and the denture entry mixed a dental product with a pharmacy product. | Per-product merchants added for the 8 products that need them. Regenerated. |
| 2 | `GRAB BAR 24IN SS` was on 5 of 20 receipts: the retail `needs_prescription` pool had 4 products, so the verdict quota kept landing on it. A model could learn the product instead of the rule. | 7 products added, each supported by its cited section. Now no product appears more than 7 times in 441 items. |
| 3 | Receipts from "other" merchants mix unrelated goods (bread, an insurance premium and swim lessons on one receipt). | Kept as a known limitation: "other" is a catch-all in DATA.md's merchant mix. It doesn't affect verdict labels. |
| 4 | `HYDROCORT 1% CRM` cites `elist:otc-antibiotic-ointment`, whose ID reads like antibiotics only. | Label is correct (the entry's names include hydrocortisone and anti-itch cream). Left as is. |

No verdict label was found to be wrong.

## Pass 2: owner (human), pending

DATA.md expects a human check. For each receipt above, open `data/receipts/<id>.png` next to
`data/golden/<id>.json`, and write a row here for anything that's wrong:

| Receipt | Item | Label | Should be | Source |
|---|---|---|---|---|
