# Eval report: full suite

| | |
|---|---|
| Date | 2026-10-28 |
| Git SHA | `946ee9f` |
| Models | extract `claude-haiku-5-5`, decide `claude-sonnet-5-5` (effort `low`) |
| Backend | `claude_code` |
| Retrieval | `hybrid`, top 5, citation expansion on |
| Prompt versions | extract `1`, decide `2` |
| Cases | 60 receipts, 441 items |
| Spend this run | $1.3100 (0 of 120 calls replayed from cache) |

## Gates (EVALS.md §3)

| Metric | Result | Gate | Pass |
|---|---|---|---|
| Unsupported citations after validation | 0 | 0 | yes |
| Over-approval rate | 0.0% | ≤ 3% | yes |
| Verdict accuracy | 98.2% | ≥ 90% | yes |
| Item recall (extraction) | 100.0% | ≥ 95% | yes |
| Redaction leaks | 0 | 0 | yes |

## Decisions (EVALS.md §2.3)

| Metric | Value |
|---|---|
| Verdict accuracy | 98.2% (441 items) |
| Over-approvals (not eligible marked eligible) | 0 of 130 |
| `needs_review` rate | 7.0% (golden: 5.2%) |
| Unsupported citations before validation | 5 of 1098 |
| Verdicts with no citation after validation (other than needs_review) | 0 |

Per class (golden verdict):

| Golden verdict | Items | Accuracy |
|---|---|---|
| eligible | 202 | 98.0% |
| not_eligible | 130 | 97.7% |
| dual_purpose | 41 | 100.0% |
| needs_prescription | 45 | 97.8% |
| needs_review | 23 | 100.0% |

Confusion matrix (rows: golden, columns: predicted):

| | eligible | not_eligible | dual_purpose | needs_prescription | needs_review | missing |
|---|---|---|---|---|---|---|
| **eligible** | 198 | 0 | 0 | 0 | 4 | 0 |
| **not_eligible** | 0 | 127 | 0 | 0 | 3 | 0 |
| **dual_purpose** | 0 | 0 | 41 | 0 | 0 | 0 |
| **needs_prescription** | 0 | 0 | 0 | 44 | 1 | 0 |
| **needs_review** | 0 | 0 | 0 | 0 | 23 | 0 |

## Extraction (EVALS.md §2.1)

| Metric | Value |
|---|---|
| Item recall / precision | 100.0% / 100.0% |
| Amount / quantity exact | 100.0% / 100.0% |
| Merchant / type / date / total | 100.0% / 98.3% / 100.0% / 100.0% |
| Totals mismatch caught | 100.0% (false alarms: 0) |
| Unreadable lines (golden `needs_review`) with low name confidence | 20 of 23 |
| Other items with low name confidence | 2 of 418 |
| Receipts that failed | 0 |

Calibration (amount field): 0.00-0.60: 0 items, n/a correct, 0.60-0.80: 0 items, n/a correct, 0.80-0.95: 5 items, 100.0% correct, 0.95-1.00: 436 items, 100.0% correct

## Safety (EVALS.md §2.5)

Personal-data values from the golden labels found in text sent to the model: **0**.

## Cost and latency (EVALS.md §2.6)

| Metric | Value |
|---|---|
| Cost per receipt (uncached run) | $0.0218 |
| … of which `extract` | $0.0010 |
| … of which `decide` | $0.0209 |
| Mean prompt / output tokens per call | 9529 / 1187 |
| Prompt tokens read from prompt cache | 82.9% |
| Latency per receipt, mean / p95 | 13.3 s / 17.7 s |

Cost is priced from `llm/pricing.py` at API list prices. On the `claude_code` backend
the calls run on a Claude subscription, so this is the API-equivalent cost.

## 10 worst failures

| Receipt | Item | Expected | Actual | Trace |
|---|---|---|---|---|
| r0020 | `EGGS LG DZ` | not_eligible | needs_review | `a7ba9bd86cb6` |
| r0027 | `ADAPALENE 0.1% GEL 15G` | eligible | needs_review | `e233acdd686a` |
| r0030 | `SVC DOG TRAINING FEE` | eligible | needs_review | `7e98d6727474` |
| r0031 | `HEALTH INST TREATMENT` | needs_prescription | needs_review | `83e3cb363628` |
| r0031 | `ASSISTED LIVING DAILY` | not_eligible | needs_review | `83e3cb363628` |
| r0041 | `ASSISTED LIVING DAILY` | not_eligible | needs_review | `2e7bb43fc15d` |
| r0051 | `SVC DOG TRAINING FEE` | eligible | needs_review | `7901c2ce364a` |
| r0053 | `CONTACT LENS FITTING` | eligible | needs_review | `ab10770668ac` |
