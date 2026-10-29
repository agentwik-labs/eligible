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


def engineering() -> dict[str, Any]:
    latest = REPORTS / "latest.json"
    ablation = REPORTS / "retrieval-ablation.md"
    devlog = ROOT / "docs" / "devlog.json"
    return {
        "devlog": json.loads(devlog.read_text()) if devlog.exists() else None,
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
