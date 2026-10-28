# Eval report: full suite

| | |
|---|---|
| Date | 2026-10-28 |
| Git SHA | `b4529ca` |
| Models | extract `claude-sonnet-5-5` (effort `low`) |
| Backend | `claude_code` |
| Prompt versions | extract `1` |
| Cases | 60 receipts, 441 items |
| Spend this run | $0.0000 (60 of 60 calls replayed from cache) |

## Gates

| Metric | Result | Gate | Pass |
|---|---|---|---|
| Item recall | 100.0% | ≥ 95% | yes |
| Redaction leaks | 0 | 0 | yes |

## Extraction (EVALS.md §2.1)

| Metric | Value |
|---|---|
| Item recall | 100.0% |
| Item precision | 100.0% |
| Amount exact match (matched items) | 100.0% |
| Quantity exact match | 100.0% |
| Merchant name | 100.0% |
| Merchant type | 100.0% |
| Date | 100.0% |
| Total | 100.0% |
| Totals mismatch caught | 100.0% (false alarms: 0) |
| Fields flagged below 0.6 confidence | 24 |
| Unreadable lines (golden `needs_review`) with low name confidence | 23 of 23 |
| Other items with low name confidence | 1 of 418 |
| Receipts that failed to extract | 0 |

### Calibration (amount field)

| Reported confidence | Items | Amount correct |
|---|---|---|
| 0.00-0.60 | 0 | n/a |
| 0.60-0.80 | 0 | n/a |
| 0.80-0.95 | 0 | n/a |
| 0.95-1.00 | 441 | 100.0% |

## Safety (EVALS.md §2.5)

Personal-data values from the golden labels found in text sent to the model: **0**.

## Cost and latency (EVALS.md §2.6)

| Metric | Value |
|---|---|
| Cost per receipt, this run | $0.0000 |
| Cost per receipt, uncached first run | $0.0146 |
| Mean prompt / output tokens per call | 0 / 0 |
| Prompt tokens read from prompt cache | 0.0% |
| Saved by prompt caching | $0.0000 |
| Latency mean / p95 (API calls) | 0 ms / 0 ms |

Cost is priced from `llm/pricing.py` at API list prices. On the `claude_code` backend
the calls run on a Claude subscription, so this is the API-equivalent cost.

## 10 worst failures

None.
