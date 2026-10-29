# Reason quality (LLM-as-judge)

2026-10-29, git `39baca4`, judge `claude-haiku-5-5` (prompt v1), 441 reasons from the full suite.

| Scale | Mean (1-5) | Scored 4 or 5 |
|---|---|---|
| faithful | 4.2 | 80.3% |
| correct | 4.71 | 95.5% |
| clear | 4.29 | 87.3% |

## Is the judge trustworthy?

- Synthetic controls: the judge scored the real reason above a reason swapped in from a different-verdict item in **20 of 20** pairs.
- Human labels: **0 of 20** (`data/judge_labels.json`; fill in faithful/correct/clear, 1-5). EVALS.md requires 80% agreement on 20 labels before these scores are trusted; until then they are reported as unvalidated.
