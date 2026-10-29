"""Write evals/reports/failures-<date>.md: every wrong verdict with its cause (PLAN M5).

uv run python -m evals.failures        # replays the response cache: no model calls, $0
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

from eligible.config import get_settings
from eligible.llm.factory import build_client
from eligible.pipeline import Checker
from evals.metrics import match_items
from evals.run import REPORTS, load_cases


def main() -> None:
    settings = get_settings().model_copy(
        update={"llm_mode": "replay", "ledger_path": Path("logs/failures.jsonl")}
    )
    checker = Checker(settings, build_client(settings))
    causes: Counter[str] = Counter()
    rows = []
    for case in load_cases("full"):
        result = checker.check(case.text)
        by_item = {id(r.item): r for r in result.items}
        pairs = match_items(case.golden.items, [r.item for r in result.items])
        for gold, extracted in pairs:
            r = by_item[id(extracted)]
            if r.verdict == gold.verdict:
                continue
            cause = ", ".join(r.flags) or "model chose it"
            causes[cause] += 1
            rows.append(
                f"| {case.golden.receipt_id} | `{gold.raw_text}` | {gold.verdict} | {r.verdict} | "
                f"{cause} | `{gold.gold_source_ids[0]}` | {r.reason[:120]} |"
            )
    lines = [
        f"# Failures, {date.today().isoformat()}",
        "",
        "Every item whose verdict differs from its label in the full suite, replayed from the",
        "response cache. Cause is the validation flag, or 'model chose it' when the model's own",
        "verdict was wrong.",
        "",
        "| Cause | Items |",
        "|---|---|",
        *[f"| {c} | {n} |" for c, n in causes.most_common()],
        "",
        "| Receipt | Item | Label | Got | Cause | Rule that applies | Model's reason |",
        "|---|---|---|---|---|---|---|",
        *rows,
    ]
    out = REPORTS / f"failures-{date.today().isoformat()}.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"{len(rows)} failures -> {out}")


if __name__ == "__main__":
    main()
