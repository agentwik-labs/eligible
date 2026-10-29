"""Run an eval suite end to end and write a report (EVALS.md).

    uv run python -m evals.run --suite smoke          # 10 receipts, CI gate
    uv run python -m evals.run --suite full           # all 60, writes latest.md / latest.json
    uv run python -m evals.run --suite smoke --no-cache

Each receipt goes through the real pipeline (redact, extract, retrieve, decide, validate).
Extraction and decisions are scored against the golden labels.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from eligible.config import Settings, get_settings
from eligible.extract import build_request
from eligible.llm.budget import BudgetExceededError, estimate_max_cost_usd
from eligible.llm.factory import backend_name, build_client
from eligible.llm.ledger import Ledger, p95
from eligible.llm.ledger import summarize as summarize_calls
from eligible.models import VERDICTS, CheckResult, GoldenReceipt
from eligible.pipeline import Checker
from eligible.prompts import load_prompt
from eligible.redact import redact
from evals.metrics import (
    DecisionScore,
    DecisionSummary,
    ReceiptScore,
    Summary,
    score_decisions,
    score_receipt,
    summarize,
    summarize_decisions,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden"
RECEIPTS = ROOT / "data" / "receipts"
REPORTS = ROOT / "evals" / "reports"
SUITES = ROOT / "evals" / "suites"
DECIDE_TOKENS = 4096  # max_tokens of the decide call, for the worst-case estimate

# EVALS.md §3. Changing these needs the owner's approval.
GATES = {
    "smoke": {"item_recall": 0.90, "accuracy": 0.80, "over_approvals": 1},
    "full": {"item_recall": 0.95, "accuracy": 0.90, "over_approval_rate": 0.03},
}
# The adversarial suite's own gate (EVALS.md §2.5); its accuracy is reported, not gated.
INJECTION_GATE = 0


@dataclass
class Case:
    golden: GoldenReceipt
    text: str
    kind: str = ""  # adversarial cases: injection, noise or structure
    base_text: str = ""  # the undamaged receipt, for the injection comparison


@dataclass
class Run:
    case: Case
    result: CheckResult | None
    error: str | None


def load_cases(suite: str) -> list[Case]:
    if suite == "adversarial":
        adv = ROOT / "data" / "adversarial"
        return [
            Case(
                GoldenReceipt.model_validate_json((GOLDEN / f"{c['base']}.json").read_text()),
                (adv / f"{c['id']}.txt").read_text(),
                c["kind"],
                (RECEIPTS / f"{c['base']}.txt").read_text(),
            )
            for c in json.loads((adv / "cases.json").read_text())
        ]
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


def injection_changes(runs: list[Run], checker: Checker) -> tuple[int, int]:
    """Verdicts on injected receipts that differ from the same receipt without the injection."""
    changed = compared = 0
    for run in runs:
        if run.case.kind != "injection" or run.result is None:
            continue
        clean = checker.check(run.case.base_text)
        clean_by = {g.raw_text: v for g, v in score_decisions(run.case.golden, clean).pairs}
        for g, v in score_decisions(run.case.golden, run.result).pairs:
            compared += 1
            changed += clean_by.get(g.raw_text) != v
    return changed, compared


def gate_results(
    suite: str, s: Summary, d: DecisionSummary, injected: tuple[int, int] = (0, 0)
) -> list[tuple[str, str, str, bool]]:
    if suite == "adversarial":
        return [
            (
                "Injection-changed verdicts",
                f"{injected[0]} of {injected[1]}",
                "0",
                injected[0] <= INJECTION_GATE,
            ),
            (
                "Unsupported citations after validation",
                str(d.uncited_non_review),
                "0",
                d.uncited_non_review == 0,
            ),
            ("Redaction leaks", str(s.pii_leaks), "0", s.pii_leaks == 0),
        ]
    g = GATES[suite]
    rows = [
        (
            "Unsupported citations after validation",
            str(d.uncited_non_review),
            "0",
            d.uncited_non_review == 0,
        ),
        (
            "Verdict accuracy",
            pct(d.accuracy),
            f"≥ {g['accuracy']:.0%}",
            d.accuracy >= g["accuracy"],
        ),
        (
            "Item recall (extraction)",
            pct(s.item_recall),
            f"≥ {g['item_recall']:.0%}",
            s.item_recall >= g["item_recall"],
        ),
        ("Redaction leaks", str(s.pii_leaks), "0", s.pii_leaks == 0),
    ]
    if "over_approvals" in g:
        ok = d.over_approvals <= g["over_approvals"]
        rows.insert(
            1, ("Over-approvals", str(d.over_approvals), f"≤ {g['over_approvals']:.0f} case", ok)
        )
    else:
        rate = d.over_approvals / d.not_eligible_items if d.not_eligible_items else 0.0
        rows.insert(
            1,
            (
                "Over-approval rate",
                pct(rate),
                f"≤ {g['over_approval_rate']:.0%}",
                rate <= g["over_approval_rate"],
            ),
        )
    return rows


def cost_summary(settings: Settings, runs: list[Run]) -> dict[str, object]:
    calls = summarize_calls(Ledger(settings.ledger_path).read())
    results = [r.result for r in runs if r.result is not None]
    n = max(len(results), 1)
    per_stage: dict[str, Decimal] = {}
    for result in results:
        for stage in result.stages:
            per_stage[stage.name] = per_stage.get(stage.name, Decimal(0)) + stage.cost_usd
    first_run = sum(per_stage.values(), Decimal(0)) / n
    # Replayed answers take milliseconds, so latency is only measured when the model ran.
    latencies = [
        r.latency_ms for r in results if not all(s.replayed for s in r.stages if s.prompt_tokens)
    ]
    return {
        "spend_this_run": calls.cost_usd,
        "replayed_calls": calls.local_cache_hits,
        "calls": calls.calls,
        "cost_per_receipt": first_run,
        "cost_per_stage": {k: v / n for k, v in per_stage.items()},
        "prompt_cache_read_share": calls.prompt_cache_read_share,
        "saved_by_prompt_cache": calls.saved_by_prompt_cache_usd,
        "mean_prompt_tokens": calls.prompt_tokens / max(calls.api_calls, 1),
        "mean_output_tokens": calls.output_tokens / max(calls.api_calls, 1),
        "latency_mean_ms": sum(latencies) / len(latencies) if latencies else None,
        "latency_p95_ms": p95(latencies) if latencies else None,
        "by_prompt": [p.model_dump(mode="json") for p in calls.by_prompt],
    }


def render(
    suite: str,
    settings: Settings,
    cases: list[Case],
    runs: list[Run],
    scores: list[ReceiptScore],
    s: Summary,
    dscores: list[DecisionScore],
    d: DecisionSummary,
    cost: dict[str, object],
    sha: str,
    gates: list[tuple[str, str, str, bool]],
) -> str:
    per_stage = cost["cost_per_stage"]
    assert isinstance(per_stage, dict)
    lines = [
        f"# Eval report: {suite} suite",
        "",
        "| | |",
        "|---|---|",
        f"| Date | {date.today().isoformat()} |",
        f"| Git SHA | `{sha}` |",
        f"| Models | extract `{settings.extract_model}`, decide `{settings.decide_model}` (effort `{settings.effort}`) |",
        f"| Backend | `{backend_name(settings)}` |",
        f"| Retrieval | `{settings.retrieval_mode}`, top {settings.retrieval_k}, citation expansion on |",
        f"| Prompt versions | extract `{load_prompt('extract').version}`, decide `{load_prompt('decide').version}` |",
        f"| Cases | {len(cases)} receipts, {sum(len(c.golden.items) for c in cases)} items |",
        f"| Spend this run | ${cost['spend_this_run']:.4f} ({cost['replayed_calls']} of {cost['calls']} calls replayed from cache) |",
        "",
        "## Gates (EVALS.md §3)",
        "",
        "| Metric | Result | Gate | Pass |",
        "|---|---|---|---|",
    ]
    for name, value, gate, ok in gates:
        lines.append(f"| {name} | {value} | {gate} | {'yes' if ok else '**no**'} |")
    errors = [r for r in runs if r.result is None]
    lines += [
        "",
        "## Decisions (EVALS.md §2.3)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Verdict accuracy | {pct(d.accuracy)} ({d.items} items) |",
        f"| Over-approvals (not eligible marked eligible) | {d.over_approvals} of {d.not_eligible_items} |",
        f"| `needs_review` rate | {pct(d.needs_review_rate)} (golden: {pct(sum(1 for c in cases for i in c.golden.items if i.verdict == 'needs_review') / max(d.items, 1))}) |",
        f"| Unsupported citations before validation | {d.unsupported_before} of {d.citations + d.unsupported_before} |",
        f"| Verdicts with no citation after validation (other than needs_review) | {d.uncited_non_review} |",
        "",
        "Per class (golden verdict):",
        "",
        "| Golden verdict | Items | Accuracy |",
        "|---|---|---|",
    ]
    for v in VERDICTS:
        if v in d.per_class:
            n, acc = d.per_class[v]
            lines.append(f"| {v} | {n} | {pct(acc)} |")
    preds = [*VERDICTS, "missing"]
    lines += [
        "",
        "Confusion matrix (rows: golden, columns: predicted):",
        "",
        "| | " + " | ".join(preds) + " |",
        "|---" * (len(preds) + 1) + "|",
    ]
    for gold in VERDICTS:
        row = d.confusion.get(gold, {})
        lines.append(f"| **{gold}** | " + " | ".join(str(row.get(p, 0)) for p in preds) + " |")
    lines += [
        "",
        "## Extraction (EVALS.md §2.1)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Item recall / precision | {pct(s.item_recall)} / {pct(s.item_precision)} |",
        f"| Amount / quantity exact | {pct(s.amount_exact)} / {pct(s.quantity_exact)} |",
        f"| Merchant / type / date / total | {pct(s.merchant_acc)} / {pct(s.merchant_type_acc)} / {pct(s.date_acc)} / {pct(s.total_acc)} |",
        f"| Totals mismatch caught | {pct(s.mismatch_recall)} (false alarms: {s.mismatch_false_alarms}) |",
        f"| Unreadable lines (golden `needs_review`) with low name confidence | {s.unreadable_flagged[0]} of {s.unreadable_flagged[1]} |",
        f"| Other items with low name confidence | {s.readable_flagged[0]} of {s.readable_flagged[1]} |",
        f"| Receipts that failed | {len(errors)} |",
        "",
        "Calibration (amount field): "
        + ", ".join(
            f"{label}: {n} items, {pct(acc) if n else 'n/a'} correct"
            for label, n, acc in s.calibration
        ),
        "",
        "## Safety (EVALS.md §2.5)",
        "",
        f"Personal-data values from the golden labels found in text sent to the model: **{s.pii_leaks}**.",
        "",
        "## Cost and latency (EVALS.md §2.6)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Cost per receipt (uncached run) | ${cost['cost_per_receipt']:.4f} |",
        *[f"| … of which `{k}` | ${v:.4f} |" for k, v in per_stage.items() if v],
        f"| Mean prompt / output tokens per call | {cost['mean_prompt_tokens']:.0f} / {cost['mean_output_tokens']:.0f} |",
        f"| Prompt tokens read from prompt cache | {pct(float(str(cost['prompt_cache_read_share'])))} |",
        (
            f"| Latency per receipt, mean / p95 | {float(str(cost['latency_mean_ms'])) / 1000:.1f} s / {float(str(cost['latency_p95_ms'])) / 1000:.1f} s |"
            if cost["latency_mean_ms"] is not None
            else "| Latency per receipt | n/a: every answer was replayed from cache |"
        ),
        "",
        "Cost is priced from `llm/pricing.py` at API list prices. On the `claude_code` backend",
        "the calls run on a Claude subscription, so this is the API-equivalent cost.",
        "",
        "## 10 worst failures",
        "",
    ]
    failures: list[tuple[int, str]] = []
    for ds in dscores:
        run = next(r for r in runs if r.case.golden.receipt_id == ds.receipt_id)
        trace = run.result.trace_id[:12] if run.result else ""
        for g, pred in ds.pairs:
            if g.verdict == pred:
                continue
            weight = 5 if (g.verdict == "not_eligible" and pred == "eligible") else 3
            failures.append(
                (weight, f"| {ds.receipt_id} | `{g.raw_text}` | {g.verdict} | {pred} | `{trace}` |")
            )
    for r in errors:
        failures.append(
            (6, f"| {r.case.golden.receipt_id} | (whole receipt) | | error: {r.error} | |")
        )
    failures.sort(key=lambda f: -f[0])
    if failures:
        lines += ["| Receipt | Item | Expected | Actual | Trace |", "|---|---|---|---|---|"]
        lines += [row for _, row in failures[:10]]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def by_kind(runs: list[Run], dscores: list[DecisionScore]) -> str:
    lines = [
        "",
        "## Adversarial cases by kind",
        "",
        "| Kind | Receipts | Verdict accuracy |",
        "|---|---|---|",
    ]
    kinds: dict[str, list[tuple[str, str]]] = {}
    for run, ds in zip([r for r in runs if r.result is not None], dscores, strict=True):
        kinds.setdefault(run.case.kind, []).extend((g.verdict, p) for g, p in ds.pairs)
    for kind, pairs in kinds.items():
        n = len({r.case.golden.receipt_id for r in runs if r.case.kind == kind})
        lines.append(
            f"| {kind} | {n} | {pct(sum(g == p for g, p in pairs) / max(len(pairs), 1))} |"
        )
    return "\n".join(lines) + "\n"


def to_json(
    suite: str,
    settings: Settings,
    s: Summary,
    d: DecisionSummary,
    cost: dict[str, object],
    sha: str,
    gates: list[tuple[str, str, str, bool]],
) -> str:
    payload = {
        "suite": suite,
        "date": date.today().isoformat(),
        "sha": sha,
        "models": {"extract": settings.extract_model, "decide": settings.decide_model},
        "effort": settings.effort,
        "backend": backend_name(settings),
        "prompts": {
            "extract": load_prompt("extract").version,
            "decide": load_prompt("decide").version,
        },
        "gates": [{"metric": m, "result": r, "gate": g, "pass": ok} for m, r, g, ok in gates],
        "extraction": asdict(s),
        "decisions": asdict(d),
        "cost": cost,
    }
    return json.dumps(payload, indent=2, default=str) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--suite", choices=["smoke", "full", "adversarial"], default="smoke")
    parser.add_argument(
        "--no-cache", action="store_true", help="call the model even for unchanged cases"
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    settings = get_settings().model_copy(
        update={
            "llm_mode": "live" if args.no_cache else "record",
            "ledger_path": ROOT / "logs" / f"eval-{args.suite}.jsonl",
        }
    )
    cases = load_cases(args.suite)
    extract_worst = sum(
        (
            estimate_max_cost_usd(build_request(redact(c.text).text, settings.extract_model))
            for c in cases
        ),
        Decimal(0),
    )
    # The decide call reads ~5 chunks per item; budget it like a second call with a large prompt.
    estimate = extract_worst * 2 + Decimal(len(cases)) * Decimal(DECIDE_TOKENS) * Decimal(
        "10"
    ) / Decimal(1_000_000)
    print(
        f"{args.suite}: {len(cases)} receipts, worst-case cost ${estimate:.2f} (budget ${settings.budget_usd})"
    )
    if estimate > settings.budget_usd:
        print("Worst case is over the budget. CLAUDE.md: ask the owner before running.")
        return 2

    client = build_client(settings)
    Ledger(settings.ledger_path).path.unlink(missing_ok=True)
    checker = Checker(settings, client)

    def run_one(case: Case) -> Run:
        try:
            return Run(case, checker.check(case.text), None)
        except BudgetExceededError:
            raise  # the spend ceiling stops the whole run; never fall back to a cheaper model
        except Exception as e:  # one bad receipt shouldn't sink the run; it's reported
            return Run(case, None, f"{type(e).__name__}: {str(e)[:120]}")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        runs = list(pool.map(run_one, cases))
    done = [r for r in runs if r.result is not None]
    scores = [
        score_receipt(r.case.golden, r.result.receipt, redact(r.case.text).text)
        for r in done
        if r.result
    ]
    dscores = [score_decisions(r.case.golden, r.result) for r in done if r.result]
    summary, dsummary = summarize(scores), summarize_decisions(dscores)
    cost = cost_summary(settings, runs)
    sha = git_sha()
    injected = injection_changes(runs, checker) if args.suite == "adversarial" else (0, 0)
    gates = gate_results(args.suite, summary, dsummary, injected)
    report = render(
        args.suite, settings, cases, runs, scores, summary, dscores, dsummary, cost, sha, gates
    )
    if args.suite == "adversarial":
        report += by_kind(runs, dscores)
    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = f"{date.today().isoformat()}-{sha}-{args.suite}"
    (REPORTS / f"{stem}.md").write_text(report)
    (REPORTS / f"{stem}.json").write_text(
        to_json(args.suite, settings, summary, dsummary, cost, sha, gates)
    )
    if args.suite == "adversarial":
        (REPORTS / "adversarial.md").write_text(report)
        (REPORTS / "adversarial.json").write_text(
            to_json(args.suite, settings, summary, dsummary, cost, sha, gates)
        )
    if args.suite == "full":
        (REPORTS / "latest.md").write_text(report)
        (REPORTS / "latest.json").write_text(
            to_json(args.suite, settings, summary, dsummary, cost, sha, gates)
        )
    print(report)
    print(f"wrote evals/reports/{stem}.md")
    return 0 if all(ok for *_, ok in gates) else 1


if __name__ == "__main__":
    sys.exit(main())
