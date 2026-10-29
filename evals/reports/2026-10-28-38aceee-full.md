# Eval report: full suite

| | |
|---|---|
| Date | 2026-10-28 |
| Git SHA | `38aceee` |
| Models | extract `claude-sonnet-5-5`, decide `claude-sonnet-5-5` (effort `low`) |
| Backend | `claude_code` |
| Retrieval | `hybrid`, top 5, citation expansion on |
| Prompt versions | extract `1`, decide `1` |
| Cases | 60 receipts, 441 items |
| Spend this run | $1.9274 (65 of 120 calls replayed from cache) |

## Gates (EVALS.md §3)

| Metric | Result | Gate | Pass |
|---|---|---|---|
| Unsupported citations after validation | 0 | 0 | yes |
| Over-approval rate | 0.0% | ≤ 3% | yes |
| Verdict accuracy | 92.7% | ≥ 90% | yes |
| Item recall (extraction) | 100.0% | ≥ 95% | yes |
| Redaction leaks | 0 | 0 | yes |

## Decisions (EVALS.md §2.3)

| Metric | Value |
|---|---|
| Verdict accuracy | 92.7% (441 items) |
| Over-approvals (not eligible marked eligible) | 0 of 130 |
| `needs_review` rate | 12.2% (golden: 5.2%) |
| Unsupported citations before validation | 28 of 917 |
| Verdicts with no citation after validation (other than needs_review) | 0 |

Per class (golden verdict):

| Golden verdict | Items | Accuracy |
|---|---|---|
| eligible | 202 | 93.1% |
| not_eligible | 130 | 89.2% |
| dual_purpose | 41 | 100.0% |
| needs_prescription | 45 | 91.1% |
| needs_review | 23 | 100.0% |

Confusion matrix (rows: golden, columns: predicted):

| | eligible | not_eligible | dual_purpose | needs_prescription | needs_review | missing |
|---|---|---|---|---|---|---|
| **eligible** | 188 | 0 | 0 | 0 | 14 | 0 |
| **not_eligible** | 0 | 116 | 0 | 1 | 13 | 0 |
| **dual_purpose** | 0 | 0 | 41 | 0 | 0 | 0 |
| **needs_prescription** | 0 | 0 | 0 | 41 | 4 | 0 |
| **needs_review** | 0 | 0 | 0 | 0 | 23 | 0 |

## Extraction (EVALS.md §2.1)

| Metric | Value |
|---|---|
| Item recall / precision | 100.0% / 100.0% |
| Amount / quantity exact | 100.0% / 100.0% |
| Merchant / type / date / total | 100.0% / 100.0% / 100.0% / 100.0% |
| Totals mismatch caught | 100.0% (false alarms: 0) |
| Unreadable lines (golden `needs_review`) with low name confidence | 23 of 23 |
| Other items with low name confidence | 1 of 418 |
| Receipts that failed | 0 |

Calibration (amount field): 0.00-0.60: 0 items, n/a correct, 0.60-0.80: 0 items, n/a correct, 0.80-0.95: 0 items, n/a correct, 0.95-1.00: 441 items, 100.0% correct

## Safety (EVALS.md §2.5)

Personal-data values from the golden labels found in text sent to the model: **0**.

## Cost and latency (EVALS.md §2.6)

| Metric | Value |
|---|---|
| Cost per receipt (uncached run) | $0.0500 |
| … of which `extract` | $0.0146 |
| … of which `decide` | $0.0353 |
| Mean prompt / output tokens per call | 8179 / 714 |
| Prompt tokens read from prompt cache | 15.5% |
| Latency per receipt, mean / p95 | 6.3 s / 9.3 s |

Cost is priced from `llm/pricing.py` at API list prices. On the `claude_code` backend
the calls run on a Claude subscription, so this is the API-equivalent cost.

## 10 worst failures

| Receipt | Item | Expected | Actual | Trace |
|---|---|---|---|---|
| r0001 | `RX LENS AR COATING` | eligible | needs_review | `27e5db71264c` |
| r0001 | `CONTACT LENS FITTING` | eligible | needs_review | `27e5db71264c` |
| r0002 | `WHOLE MILK GAL` | not_eligible | needs_review | `3b2672ec71e6` |
| r0008 | `CHIPS SEA SALT 8OZ` | not_eligible | needs_review | `12d0c3abd022` |
| r0013 | `WHOLE MILK GAL` | not_eligible | needs_review | `c0038b62c7d8` |
| r0013 | `FLEA TICK DOG 3DOSE` | not_eligible | needs_review | `c0038b62c7d8` |
| r0014 | `ADAPALENE 0.1% GEL 15G` | eligible | needs_review | `baf62148bf68` |
| r0015 | `NYQUIL LIQ 12OZ` | eligible | needs_review | `0589e7501024` |
| r0017 | `BREAD WHL WHT 20OZ` | not_eligible | needs_review | `a649b9f6e63c` |
| r0020 | `EGGS LG DZ` | not_eligible | needs_review | `ee1e1609ebfd` |
