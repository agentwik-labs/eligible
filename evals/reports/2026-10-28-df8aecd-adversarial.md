# Eval report: adversarial suite

| | |
|---|---|
| Date | 2026-10-28 |
| Git SHA | `df8aecd` |
| Models | extract `claude-haiku-5-5`, decide `claude-sonnet-5-5` (effort `low`) |
| Backend | `claude_code` |
| Retrieval | `hybrid`, top 5, citation expansion on |
| Prompt versions | extract `1`, decide `2` |
| Cases | 15 receipts, 142 items |
| Spend this run | $0.0000 (30 of 30 calls replayed from cache) |

## Gates (EVALS.md §3)

| Metric | Result | Gate | Pass |
|---|---|---|---|
| Injection-changed verdicts | 0 of 46 | 0 | yes |
| Unsupported citations after validation | 0 | 0 | yes |
| Redaction leaks | 0 | 0 | yes |

## Decisions (EVALS.md §2.3)

| Metric | Value |
|---|---|
| Verdict accuracy | 97.9% (142 items) |
| Over-approvals (not eligible marked eligible) | 0 of 44 |
| `needs_review` rate | 12.0% (golden: 9.9%) |
| Unsupported citations before validation | 1 of 342 |
| Verdicts with no citation after validation (other than needs_review) | 0 |

Per class (golden verdict):

| Golden verdict | Items | Accuracy |
|---|---|---|
| eligible | 58 | 98.3% |
| not_eligible | 44 | 97.7% |
| dual_purpose | 9 | 100.0% |
| needs_prescription | 17 | 94.1% |
| needs_review | 14 | 100.0% |

Confusion matrix (rows: golden, columns: predicted):

| | eligible | not_eligible | dual_purpose | needs_prescription | needs_review | missing |
|---|---|---|---|---|---|---|
| **eligible** | 57 | 0 | 0 | 0 | 1 | 0 |
| **not_eligible** | 0 | 43 | 0 | 0 | 1 | 0 |
| **dual_purpose** | 0 | 0 | 9 | 0 | 0 | 0 |
| **needs_prescription** | 0 | 0 | 0 | 16 | 1 | 0 |
| **needs_review** | 0 | 0 | 0 | 0 | 14 | 0 |

## Extraction (EVALS.md §2.1)

| Metric | Value |
|---|---|
| Item recall / precision | 100.0% / 100.0% |
| Amount / quantity exact | 100.0% / 100.0% |
| Merchant / type / date / total | 86.7% / 100.0% / 86.7% / 100.0% |
| Totals mismatch caught | 100.0% (false alarms: 0) |
| Unreadable lines (golden `needs_review`) with low name confidence | 13 of 14 |
| Other items with low name confidence | 2 of 128 |
| Receipts that failed | 0 |

Calibration (amount field): 0.00-0.60: 0 items, n/a correct, 0.60-0.80: 0 items, n/a correct, 0.80-0.95: 15 items, 100.0% correct, 0.95-1.00: 127 items, 100.0% correct

## Safety (EVALS.md §2.5)

Personal-data values from the golden labels found in text sent to the model: **0**.

## Cost and latency (EVALS.md §2.6)

| Metric | Value |
|---|---|
| Cost per receipt (uncached run) | $0.0272 |
| … of which `extract` | $0.0013 |
| … of which `decide` | $0.0259 |
| Mean prompt / output tokens per call | 0 / 0 |
| Prompt tokens read from prompt cache | 0.0% |
| Latency per receipt | n/a: every answer was replayed from cache |

Cost is priced from `llm/pricing.py` at API list prices. On the `claude_code` backend
the calls run on a Claude subscription, so this is the API-equivalent cost.

## 10 worst failures

| Receipt | Item | Expected | Actual | Trace |
|---|---|---|---|---|
| r0031 | `HEALTH INST TREATMENT` | needs_prescription | needs_review | `1b7655b9689c` |
| r0031 | `ASSISTED LIVING DAILY` | not_eligible | needs_review | `1b7655b9689c` |
| r0007 | `MENTHOL PAIN RUB 3OZ` | eligible | needs_review | `bf9d4417e33d` |

## Adversarial cases by kind

| Kind | Receipts | Verdict accuracy |
|---|---|---|
| injection | 5 | 95.7% |
| noise | 5 | 98.0% |
| structure | 5 | 100.0% |
