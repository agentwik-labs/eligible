# Eval report: full suite

| | |
|---|---|
| Date | 2026-10-28 |
| Git SHA | `09dd063` |
| Models | extract `claude-sonnet-5-5`, decide `claude-sonnet-5-5` (effort `low`) |
| Backend | `claude_code` |
| Retrieval | `hybrid`, top 5, citation expansion on |
| Prompt versions | extract `1`, decide `2` |
| Cases | 60 receipts, 441 items |
| Spend this run | $2.0268 (60 of 120 calls replayed from cache) |

## Gates (EVALS.md §3)

| Metric | Result | Gate | Pass |
|---|---|---|---|
| Unsupported citations after validation | 0 | 0 | yes |
| Over-approval rate | 0.0% | ≤ 3% | yes |
| Verdict accuracy | 97.5% | ≥ 90% | yes |
| Item recall (extraction) | 100.0% | ≥ 95% | yes |
| Redaction leaks | 0 | 0 | yes |

## Decisions (EVALS.md §2.3)

| Metric | Value |
|---|---|
| Verdict accuracy | 97.5% (441 items) |
| Over-approvals (not eligible marked eligible) | 0 of 130 |
| `needs_review` rate | 7.5% (golden: 5.2%) |
| Unsupported citations before validation | 10 of 1105 |
| Verdicts with no citation after validation (other than needs_review) | 0 |

Per class (golden verdict):

| Golden verdict | Items | Accuracy |
|---|---|---|
| eligible | 202 | 97.0% |
| not_eligible | 130 | 96.9% |
| dual_purpose | 41 | 100.0% |
| needs_prescription | 45 | 97.8% |
| needs_review | 23 | 100.0% |

Confusion matrix (rows: golden, columns: predicted):

| | eligible | not_eligible | dual_purpose | needs_prescription | needs_review | missing |
|---|---|---|---|---|---|---|
| **eligible** | 196 | 0 | 0 | 1 | 5 | 0 |
| **not_eligible** | 0 | 126 | 0 | 0 | 4 | 0 |
| **dual_purpose** | 0 | 0 | 41 | 0 | 0 | 0 |
| **needs_prescription** | 0 | 0 | 0 | 44 | 1 | 0 |
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
| Cost per receipt (uncached run) | $0.0484 |
| … of which `extract` | $0.0146 |
| … of which `decide` | $0.0338 |
| Mean prompt / output tokens per call | 18405 / 676 |
| Prompt tokens read from prompt cache | 66.6% |
| Latency per receipt, mean / p95 | 6.0 s / 8.5 s |

Cost is priced from `llm/pricing.py` at API list prices. On the `claude_code` backend
the calls run on a Claude subscription, so this is the API-equivalent cost.

## 10 worst failures

| Receipt | Item | Expected | Actual | Trace |
|---|---|---|---|---|
| r0001 | `CONTACT LENS FITTING` | eligible | needs_review | `216811ef476c` |
| r0020 | `EGGS LG DZ` | not_eligible | needs_review | `e9821cd3ccf9` |
| r0031 | `HEALTH INST TREATMENT` | needs_prescription | needs_review | `35bca5233ce4` |
| r0031 | `ASSISTED LIVING DAILY` | not_eligible | needs_review | `35bca5233ce4` |
| r0037 | `SALINE SOLN 12OZ` | eligible | needs_review | `84f162e555c8` |
| r0041 | `ASSISTED LIVING DAILY` | not_eligible | needs_review | `d682df4dd03b` |
| r0049 | `MULTI-PURP SOLN 12OZ` | eligible | needs_review | `f34b39496ce7` |
| r0051 | `SVC DOG TRAINING FEE` | eligible | needs_review | `9ba8011d9378` |
| r0052 | `CEREAL OAT 18OZ` | not_eligible | needs_review | `2bb490aa33e3` |
| r0054 | `SVC DOG TRAINING FEE` | eligible | needs_prescription | `78980b660354` |
