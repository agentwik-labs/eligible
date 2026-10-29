"""Copy the headline results into README.md from committed eval reports (CLAUDE.md rule 4).

    uv run python scripts/readme_results.py

Replaces the block between the RESULTS markers. Every number comes from
evals/reports/latest.json, evals/reports/adversarial.json or retrieval-ablation.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from eligible.showcase import markdown_table

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "evals" / "reports"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def pct(x: float) -> str:
    return f"{x:.1%}"


def table() -> str:
    full = json.loads((REPORTS / "latest.json").read_text())
    d, x, c = full["decisions"], full["extraction"], full["cost"]
    gate = {g["metric"]: g for g in full["gates"]}
    rows = [
        ("Verdict accuracy", pct(d["accuracy"]), gate["Verdict accuracy"]["gate"]),
        (
            "Ineligible items approved",
            f"{d['over_approvals']} of {d['not_eligible_items']}",
            gate["Over-approval rate"]["gate"],
        ),
        (
            "Invented citations that reached a user",
            f"{d['uncited_non_review']} ({d['unsupported_before']} caught by validation)",
            "0",
        ),
        ("Personal-data leaks to the model", str(x["pii_leaks"]), "0"),
        (
            "Line items read (recall)",
            pct(x["item_recall"]),
            gate["Item recall (extraction)"]["gate"],
        ),
    ]
    adversarial = REPORTS / "adversarial.json"
    if adversarial.exists():
        adv = {g["metric"]: g for g in json.loads(adversarial.read_text())["gates"]}
        inj = adv["Injection-changed verdicts"]
        rows.append(("Verdicts changed by prompt injection", inj["result"], inj["gate"]))
    ablation = REPORTS / "retrieval-ablation.md"
    if ablation.exists():
        head, *body = markdown_table(ablation.read_text())
        shipped = next(r for r in body if r[0] == "Hybrid + exact match + citation expansion")
        rows.append(("Retrieval recall@5", shipped[head.index("Recall@5")], "≥ 90%"))
    rows.append(
        (
            "Cost per receipt (API list prices)",
            f"${float(c['cost_per_receipt']):.4f}",
            "< $0.01 aim",
        )
    )
    if c.get("latency_p95_ms"):
        rows.append(("Latency per receipt, p95", f"{c['latency_p95_ms'] / 1000:.1f} s", "n/a"))
    lines = [
        START,
        f"From [`evals/reports/latest.md`](evals/reports/latest.md): {full['date']}, "
        f"git `{full['sha']}`, 60 synthetic receipts / {d['items']} line items, "
        f"extract `{full['models']['extract']}`, "
        f"decide `{full['models']['decide']}`.",
        "",
        "| Metric | Result | Gate or target |",
        "|---|---|---|",
        *[f"| {m} | **{v}** | {g} |" for m, v, g in rows],
        END,
    ]
    return "\n".join(lines)


def main() -> None:
    readme = ROOT / "README.md"
    text = readme.read_text()
    block = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    readme.write_text(block.sub(lambda _: table(), text))
    print("README results updated")


if __name__ == "__main__":
    main()
