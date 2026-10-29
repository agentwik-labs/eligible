# Eval report: full suite

| | |
|---|---|
| Date | 2026-10-28 |
| Git SHA | `45300dd` |
| Models | extract `claude-haiku-5-5`, decide `claude-sonnet-5-5` (effort `low`) |
| Backend | `claude_code` |
| Retrieval | `hybrid`, top 5, citation expansion on |
| Prompt versions | extract `1`, decide `2` |
| Cases | 60 receipts, 441 items |
| Spend this run | $1.3586 (7 of 120 calls replayed from cache) |

## Gates (EVALS.md §3)

| Metric | Result | Gate | Pass |
|---|---|---|---|
| Unsupported citations after validation | 0 | 0 | yes |
| Over-approval rate | 0.0% | ≤ 3% | yes |
| Verdict accuracy | 97.7% | ≥ 90% | yes |
| Item recall (extraction) | 100.0% | ≥ 95% | yes |
| Redaction leaks | 0 | 0 | yes |

## Decisions (EVALS.md §2.3)

| Metric | Value |
|---|---|
| Verdict accuracy | 97.7% (441 items) |
| Over-approvals (not eligible marked eligible) | 0 of 130 |
| `needs_review` rate | 7.5% (golden: 5.2%) |
| Unsupported citations before validation | 6 of 1099 |
| Verdicts with no citation after validation (other than needs_review) | 0 |

Per class (golden verdict):

| Golden verdict | Items | Accuracy |
|---|---|---|
| eligible | 202 | 97.0% |
| not_eligible | 130 | 97.7% |
| dual_purpose | 41 | 100.0% |
| needs_prescription | 45 | 97.8% |
| needs_review | 23 | 100.0% |

Confusion matrix (rows: golden, columns: predicted):

| | eligible | not_eligible | dual_purpose | needs_prescription | needs_review | missing |
|---|---|---|---|---|---|---|
| **eligible** | 196 | 0 | 0 | 0 | 6 | 0 |
| **not_eligible** | 0 | 127 | 0 | 0 | 3 | 0 |
| **dual_purpose** | 0 | 0 | 41 | 0 | 0 | 0 |
| **needs_prescription** | 0 | 0 | 0 | 44 | 1 | 0 |
| **needs_review** | 0 | 0 | 0 | 0 | 23 | 0 |

## Extraction (EVALS.md §2.1)

| Metric | Value |
|---|---|
| Item recall / precision | 100.0% / 100.0% |
| Amount / quantity exact | 100.0% / 100.0% |
| Merchant / type / date / total | 100.0% / 96.7% / 100.0% / 100.0% |
| Totals mismatch caught | 100.0% (false alarms: 0) |
| Unreadable lines (golden `needs_review`) with low name confidence | 22 of 23 |
| Other items with low name confidence | 2 of 418 |
| Receipts that failed | 0 |

Calibration (amount field): 0.00-0.60: 0 items, n/a correct, 0.60-0.80: 0 items, n/a correct, 0.80-0.95: 15 items, 100.0% correct, 0.95-1.00: 426 items, 100.0% correct

## Safety (EVALS.md §2.5)

Personal-data values from the golden labels found in text sent to the model: **0**.

## Cost and latency (EVALS.md §2.6)

| Metric | Value |
|---|---|
| Cost per receipt (uncached run) | $0.0245 |
| … of which `extract` | $0.0011 |
| … of which `decide` | $0.0234 |
| Mean prompt / output tokens per call | 9465 / 1262 |
| Prompt tokens read from prompt cache | 75.1% |
| Latency per receipt, mean / p95 | 14.8 s / 25.5 s |

Cost is priced from `llm/pricing.py` at API list prices. On the `claude_code` backend
the calls run on a Claude subscription, so this is the API-equivalent cost.

## 10 worst failures

| Receipt | Item | Expected | Actual | Trace |
|---|---|---|---|---|
| r0001 | `CONTACT LENS FITTING` | eligible | needs_review | `1d7b355e469d` |
| r0020 | `EGGS LG DZ` | not_eligible | needs_review | `51f154afdef1` |
| r0027 | `ADAPALENE 0.1% GEL 15G` | eligible | needs_review | `62fe3f1e84ff` |
| r0031 | `HEALTH INST TREATMENT` | needs_prescription | needs_review | `4bcaa5f8efb6` |
| r0031 | `ASSISTED LIVING DAILY` | not_eligible | needs_review | `4bcaa5f8efb6` |
| r0041 | `ASSISTED LIVING DAILY` | not_eligible | needs_review | `e56ee78e0eaa` |
| r0051 | `SVC DOG TRAINING FEE` | eligible | needs_review | `cf76e13ca528` |
| r0053 | `CONTACT LENS FITTING` | eligible | needs_review | `e5a79af02bc1` |
| r0054 | `SVC DOG TRAINING FEE` | eligible | needs_review | `bf5df009a180` |
| r0058 | `CONTACT LENS FITTING` | eligible | needs_review | `1cdd62595954` |
