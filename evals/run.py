"""Run an eval suite and write a report (EVALS.md).

    uv run python -m evals.run --suite smoke          # 10 receipts, CI gate
    uv run python -m evals.run --suite full           # all 60, writes latest.md
    uv run python -m evals.run --suite smoke --no-cache

M2 scope: redaction and extraction. Retrieval (M3) and verdicts (M4) add sections here.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from eligible.config import Settings, get_settings
from eligible.extract import Extraction, build_request, extract
from eligible.llm.budget import BudgetExceededError, estimate_max_cost_usd
from eligible.llm.factory import backend_name, build_client
from eligible.llm.ledger import Ledger, p95
from eligible.llm.ledger import summarize as summarize_calls
from eligible.models import GoldenReceipt
from eligible.prompts import load_prompt
from eligible.redact import redact
from evals.metrics import ReceiptScore, Summary, score_receipt, summarize

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden"
RECEIPTS = ROOT / "data" / "receipts"
REPORTS = ROOT / "evals" / "reports"
SUITES = ROOT / "evals" / "suites"

# EVALS.md §3. Changing these needs the owner's approval.
GATES = {
    "smoke": {"item_recall": 0.90, "pii_leaks": 0},
    "full": {"item_recall": 0.95, "pii_leaks": 0},
}


@dataclass
class Case:
    golden: GoldenReceipt
    text: str


def load_cases(suite: str) -> list[Case]:
    if suite == "full":
        ids = sorted(p.stem for p in GOLDEN.glob("r*.json"))
    else:
        ids = json.loads((SUITES / f"{suite}.json").read_text())["receipts"]
    return [
        Case(
            GoldenReceipt.model_validate_json((GOLDEN / f"{rid}.json").read_text()),
            (RECEIPTS / f"{rid}.txt").read_text(),
        )
        for rid in ids
    ]


def git_sha() -> str:
    git = shutil.which("git") or "git"
    out = subprocess.run([git, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)  # noqa: S603
    return out.stdout.strip() or "nogit"


def pct(x: float) -> str:
    return f"{x:.1%}"


def gate_results(suite: str, s: Summary) -> list[tuple[str, str, str, bool]]:
    gates = GATES[suite]
    return [
        (
            "Item recall",
            pct(s.item_recall),
            f"≥ {gates['item_recall']:.0%}",
            s.item_recall >= gates["item_recall"],
        ),
        ("Redaction leaks", str(s.pii_leaks), "0", s.pii_leaks <= gates["pii_leaks"]),
    ]


def render(
    suite: str,
    settings: Settings,
    cases: list[Case],
    runs: list[tuple[Case, Extraction | None, str | None]],
    scores: list[ReceiptScore],
    s: Summary,
    sha: str,
) -> str:
    responses = [x.response for _, x, _ in runs if x is not None]
    calls = summarize_calls(responses)
    api = [r for r in responses if r.source == "api"]
    per_receipt = calls.cost_usd / len(cases) if cases else Decimal(0)
    replayed_cost = sum((r.avoided_cost_usd for r in responses), Decimal(0))
    first_run_cost = (calls.cost_usd + replayed_cost) / len(cases) if cases else Decimal(0)
    lines = [
        f"# Eval report: {suite} suite",
        "",
        "| | |",
        "|---|---|",
        f"| Date | {date.today().isoformat()} |",
        f"| Git SHA | `{sha}` |",
        f"| Models | extract `{settings.extract_model}` (effort `{settings.effort}`) |",
        f"| Backend | `{backend_name(settings)}` |",
        f"| Prompt versions | extract `{load_prompt('extract').version}` |",
        f"| Cases | {len(cases)} receipts, {sum(len(c.golden.items) for c in cases)} items |",
        f"| Spend this run | ${calls.cost_usd:.4f} ({calls.local_cache_hits} of {calls.calls} calls replayed from cache) |",
        "",
        "## Gates",
        "",
        "| Metric | Result | Gate | Pass |",
        "|---|---|---|---|",
    ]
    for name, value, gate, ok in gate_results(suite, s):
        lines.append(f"| {name} | {value} | {gate} | {'yes' if ok else '**no**'} |")
    errors = [(c, err) for c, x, err in runs if x is None]
    lines += [
        "",
        "## Extraction (EVALS.md §2.1)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Item recall | {pct(s.item_recall)} |",
        f"| Item precision | {pct(s.item_precision)} |",
        f"| Amount exact match (matched items) | {pct(s.amount_exact)} |",
        f"| Quantity exact match | {pct(s.quantity_exact)} |",
        f"| Merchant name | {pct(s.merchant_acc)} |",
        f"| Merchant type | {pct(s.merchant_type_acc)} |",
        f"| Date | {pct(s.date_acc)} |",
        f"| Total | {pct(s.total_acc)} |",
        f"| Totals mismatch caught | {pct(s.mismatch_recall)} (false alarms: {s.mismatch_false_alarms}) |",
        f"| Fields flagged below 0.6 confidence | {s.flagged_fields} |",
        f"| Unreadable lines (golden `needs_review`) with low name confidence | {s.unreadable_flagged[0]} of {s.unreadable_flagged[1]} |",
        f"| Other items with low name confidence | {s.readable_flagged[0]} of {s.readable_flagged[1]} |",
        f"| Receipts that failed to extract | {len(errors)} |",
        "",
        "### Calibration (amount field)",
        "",
        "| Reported confidence | Items | Amount correct |",
        "|---|---|---|",
    ]
    lines += [f"| {label} | {n} | {pct(acc) if n else 'n/a'} |" for label, n, acc in s.calibration]
    lines += [
        "",
        "## Safety (EVALS.md §2.5)",
        "",
        f"Personal-data values from the golden labels found in text sent to the model: **{s.pii_leaks}**.",
        "",
        "## Cost and latency (EVALS.md §2.6)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Cost per receipt, this run | ${per_receipt:.4f} |",
        f"| Cost per receipt, uncached first run | ${first_run_cost:.4f} |",
        f"| Mean prompt / output tokens per call | {calls.prompt_tokens / max(len(api), 1):.0f} / {calls.output_tokens / max(len(api), 1):.0f} |",
        f"| Prompt tokens read from prompt cache | {pct(calls.prompt_cache_read_share)} |",
        f"| Saved by prompt caching | ${calls.saved_by_prompt_cache_usd:.4f} |",
        f"| Latency mean / p95 (API calls) | {calls.latency_mean_ms:.0f} ms / {p95([r.latency_ms for r in api]):.0f} ms |",
        "",
        "Cost is priced from `llm/pricing.py` at API list prices. On the `claude_code` backend",
        "the calls run on a Claude subscription, so this is the API-equivalent cost.",
        "",
        "## 10 worst failures",
        "",
    ]
    failures: list[tuple[int, str]] = []
    for score in scores:
        case = next(c for c in cases if c.golden.receipt_id == score.receipt_id)
        x = next(x for c, x, _ in runs if c is case)
        key = x.response.request_key[:12] if x else "n/a"
        matched_g = {id(g) for g, _ in score.matched}
        for g in case.golden.items:
            if id(g) not in matched_g:
                failures.append(
                    (
                        3,
                        f"| {score.receipt_id} | missed item | `{g.raw_text}` {g.amount} | not extracted | `{key}` |",
                    )
                )
        for g, e in score.amount_errors:
            failures.append(
                (
                    2,
                    f"| {score.receipt_id} | wrong amount | `{g.raw_text}` {g.amount} | {e.amount} | `{key}` |",
                )
            )
        if score.mismatch_expected != score.mismatch_detected:
            what = "missed totals mismatch" if score.mismatch_expected else "false totals mismatch"
            failures.append((1, f"| {score.receipt_id} | {what} | | | `{key}` |"))
        if not score.total_ok:
            failures.append(
                (
                    1,
                    f"| {score.receipt_id} | wrong total | {case.golden.total} | {x.receipt.total if x else ''} | `{key}` |",
                )
            )
    for c, err in errors:
        failures.append((4, f"| {c.golden.receipt_id} | extraction error | | {err} | |"))
    failures.sort(key=lambda f: -f[0])
    if failures:
        lines += ["| Receipt | Failure | Expected | Actual | Trace |", "|---|---|---|---|---|"]
        lines += [row for _, row in failures[:10]]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--suite", choices=["smoke", "full"], default="smoke")
    parser.add_argument(
        "--no-cache", action="store_true", help="call the model even for unchanged cases"
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    base = get_settings()
    settings = base.model_copy(
        update={
            "llm_mode": "live" if args.no_cache else "record",
            "ledger_path": ROOT / "logs" / f"eval-{args.suite}.jsonl",
        }
    )
    cases = load_cases(args.suite)
    estimate = sum(
        (
            estimate_max_cost_usd(build_request(redact(c.text).text, settings.extract_model))
            for c in cases
        ),
        Decimal(0),
    )
    print(
        f"{args.suite}: {len(cases)} receipts, worst-case cost ${estimate:.2f} (budget ${settings.budget_usd})"
    )
    if estimate > settings.budget_usd:
        print("Worst case is over the budget. CLAUDE.md: ask the owner before running.")
        return 2

    client = build_client(settings)
    Ledger(settings.ledger_path).path.unlink(missing_ok=True)

    def run_one(case: Case) -> tuple[Case, Extraction | None, str | None]:
        try:
            return case, extract(case.text, client, settings.extract_model), None
        except BudgetExceededError:
            raise  # the spend ceiling stops the whole run; never fall back to a cheaper model
        except Exception as e:  # one bad receipt shouldn't sink the run; it's reported
            return case, None, f"{type(e).__name__}: {str(e)[:120]}"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        runs = list(pool.map(run_one, cases))
    scores = [
        score_receipt(
            c.golden,
            x.receipt,
            x.request.messages[0].content if isinstance(x.request.messages[0].content, str) else "",
        )
        for c, x, _ in runs
        if x is not None
    ]
    summary = summarize(scores)
    sha = git_sha()
    report = render(args.suite, settings, cases, runs, scores, summary, sha)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{date.today().isoformat()}-{sha}-{args.suite}.md"
    out.write_text(report)
    if args.suite == "full":
        (REPORTS / "latest.md").write_text(report)
    print(report)
    print(f"wrote {out.relative_to(ROOT)}")
    passed = all(ok for *_, ok in gate_results(args.suite, summary))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
