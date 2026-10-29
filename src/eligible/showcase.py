"""Data for the engineering page, read only from committed artifacts (CLAUDE.md rule 4)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from eligible.knowledge.eligibility import load_list
from eligible.knowledge.sources import load_sections
from eligible.llm import pricing
from eligible.llm.projection import Scenario, stages

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "evals" / "reports"


def markdown_table(text: str, after: str = "") -> list[list[str]]:
    """Rows of the first Markdown table after the line containing `after`."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if after in line), 0)
    rows: list[list[str]] = []
    for line in lines[start:]:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
        elif rows:
            break
    return rows


def decisions_log() -> list[dict[str, str]]:
    text = (ROOT / "DECISIONS.md").read_text()
    entries = []
    for block in re.split(r"\n(?=## )", text)[1:]:
        heading, _, body = block.partition("\n")
        match = re.match(r"## (\d{4}-\d{2}-\d{2}): (.+)", heading)
        if match:
            entries.append({"date": match[1], "title": match[2], "body": body.strip()})
    return entries


def production_concerns() -> list[dict[str, str]]:
    text = (ROOT / "docs" / "production-concerns.md").read_text()
    rows = []
    for match in re.finditer(r"^## \d+\. (.+?): (done|planned.*?|flagging done.*)$", text, re.M):
        rows.append({"concern": match[1], "status": match[2]})
    return rows


def projection() -> list[dict[str, Any]]:
    out = []
    for model in pricing.PRICES:
        costs = stages(Scenario(), model)
        out.append(
            {
                "model": model,
                "extract": float(costs[0].cost_usd),
                "decide": float(costs[1].cost_usd),
                "total": float(sum(c.cost_usd for c in costs)),
            }
        )
    return out


def read_json(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else None


def gate_demo() -> list[dict[str, Any]]:
    runs = []
    for path in sorted((REPORTS / "gate-demo").glob("*.json")):
        report = json.loads(path.read_text())
        d = report["decisions"]
        conditional = sum(
            d["confusion"].get(c, {}).get("eligible", 0)
            for c in ("dual_purpose", "needs_prescription", "needs_review")
        )
        runs.append(
            {
                "sha": report["sha"],
                "accuracy": d["accuracy"],
                "over_approvals": d["over_approvals"],
                "conditional_approvals": conditional,
                "passed": all(g["pass"] for g in report["gates"]),
            }
        )
    return runs


def trace_summary() -> dict[str, Any] | None:
    path = ROOT / "logs" / "traces.jsonl"
    if not path.exists():
        return None
    traces = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    live = [t for t in traces if any(s.get("model") and not s.get("replayed") for s in t["spans"])]
    if not live:
        return {"requests": len(traces), "live": 0}
    latencies = sorted(t["total_ms"] for t in live)
    return {
        "requests": len(traces),
        "live": len(live),
        "p50_ms": latencies[len(latencies) // 2],
        "p95_ms": latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))],
        "mean_cost": sum(float(t["cost_usd"]) for t in live) / len(live),
    }


def engineering() -> dict[str, Any]:
    latest = REPORTS / "latest.json"
    ablation = REPORTS / "retrieval-ablation.md"
    devlog = ROOT / "docs" / "devlog.json"
    return {
        "devlog": json.loads(devlog.read_text()) if devlog.exists() else None,
        "adversarial": read_json(REPORTS / "adversarial.json"),
        "adversarial_kinds": markdown_table(
            (REPORTS / "adversarial.md").read_text(), "Adversarial cases by kind"
        )
        if (REPORTS / "adversarial.md").exists()
        else [],
        "judge": read_json(REPORTS / "judge.json"),
        "mcp": read_json(ROOT / "docs" / "mcp-demo.json"),
        "gate_demo": gate_demo(),
        "traces": trace_summary(),
        "eval": json.loads(latest.read_text()) if latest.exists() else None,
        "ablation": markdown_table(ablation.read_text()) if ablation.exists() else [],
        "projection": projection(),
        "decisions": decisions_log(),
        "concerns": production_concerns(),
        "knowledge": {
            "sections": len(load_sections()),
            "entries": len(load_list()),
            "products": sum(len(e.products) for e in load_list()),
        },
    }
