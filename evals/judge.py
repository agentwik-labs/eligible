"""LLM-as-judge for reason quality (EVALS.md §2.4): `uv run python -m evals.judge`.

Grades every reason from the latest full run with Haiku. The pipeline itself is replayed
from the response cache, so only the judge calls cost anything.

Validating the judge: EVALS.md asks for 20 human-labelled reasons. Until those exist, the
judge is checked on synthetic controls: each real reason is paired with a reason taken
from a different item (same verdict class removed), and the judge must score the real one
higher. That shows the judge can tell matching from mismatched reasons; it doesn't replace
the human labels, and the report says so.
"""

from __future__ import annotations

import json
import random
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from eligible.config import get_settings
from eligible.llm.client import LLMClient
from eligible.llm.factory import build_client
from eligible.llm.types import LLMRequest, Message
from eligible.models import ItemResult
from eligible.pipeline import Checker
from eligible.prompts import load_prompt
from evals.metrics import match_items
from evals.run import REPORTS, git_sha, load_cases

LABELS = Path(__file__).resolve().parents[1] / "data" / "judge_labels.json"
SCORE = {"type": "integer", "minimum": 1, "maximum": 5}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "grades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "faithful": SCORE,
                    "correct": SCORE,
                    "clear": SCORE,
                },
                "required": ["index", "faithful", "correct", "clear"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["grades"],
    "additionalProperties": False,
}


class Grade(BaseModel):
    index: int
    faithful: int = Field(ge=1, le=5)
    correct: int = Field(ge=1, le=5)
    clear: int = Field(ge=1, le=5)


class Graded(BaseModel):
    item: str
    verdict: str
    reason: str
    rule: str
    sources: str


def render(rows: list[Graded]) -> str:
    out = ["<items>"]
    for i, r in enumerate(rows):
        out.append(
            f"{i}. item: {r.item}\n   verdict: {r.verdict}\n   reason: {r.reason}\n"
            f"   cited source text: {r.sources}\n   reference rule: {r.rule}"
        )
    out.append("</items>")
    return "\n".join(out)


def grade(rows: list[Graded], client: LLMClient) -> list[Grade]:
    prompt = load_prompt("judge")
    request = LLMRequest(
        model=get_settings().judge_model,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        system=prompt.text,
        messages=[Message(role="user", content=render(rows))],
        max_tokens=2048,
        effort="low",
        output_schema=SCHEMA,
    )
    response = client.complete(request)
    grades = [Grade.model_validate(g) for g in response.json_output()["grades"]]
    by_index = {g.index: g for g in grades}
    return [by_index[i] for i in range(len(rows)) if i in by_index]


def as_graded(result: ItemResult, rule: str) -> Graded:
    return Graded(
        item=result.item.name,
        verdict=result.verdict,
        reason=result.reason,
        rule=rule,
        sources=" | ".join(c.quote for c in result.citations)[:1500] or "(no citation)",
    )


def mean(grades: list[Grade], field: str) -> float:
    return statistics.mean(getattr(g, field) for g in grades) if grades else 0.0


def main() -> None:
    settings = get_settings()
    replay = settings.model_copy(
        update={"llm_mode": "replay", "ledger_path": Path("logs/judge-pipeline.jsonl")}
    )
    checker = Checker(replay, build_client(replay))
    judge_settings = settings.model_copy(update={"ledger_path": Path("logs/judge.jsonl")})
    judge = build_client(judge_settings)

    receipts: list[list[Graded]] = []
    for case in load_cases("full"):
        result = checker.check(case.text)
        by_item = {id(r.item): r for r in result.items}
        pairs = match_items(case.golden.items, [r.item for r in result.items])
        receipts.append([as_graded(by_item[id(e)], g.note) for g, e in pairs])

    with ThreadPoolExecutor(max_workers=4) as pool:
        graded = list(pool.map(lambda rows: grade(rows, judge), receipts))
    flat = [g for gs in graded for g in gs]

    # Controls: swap in a reason from an item with a different verdict.
    rng = random.Random(11)
    everything = [r for rows in receipts for r in rows]
    picks = rng.sample(everything, 20)
    bad = [
        r.model_copy(
            update={"reason": rng.choice([o for o in everything if o.verdict != r.verdict]).reason}
        )
        for r in picks
    ]
    good_grades = grade(picks, judge)
    bad_grades = grade(bad, judge)
    wins = sum(
        (g.faithful + g.correct) > (b.faithful + b.correct)
        for g, b in zip(good_grades, bad_grades, strict=False)
    )
    human = [
        h for h in (json.loads(LABELS.read_text()) if LABELS.exists() else []) if h.get("faithful")
    ]
    if not LABELS.exists():  # a ready-to-fill sheet for the owner: score each reason 1-5
        sheet = [
            {**r.model_dump(), "faithful": None, "correct": None, "clear": None} for r in picks
        ]
        LABELS.write_text(json.dumps(sheet, indent=2) + "\n")
    agreement = None
    if human:
        judged = grade([Graded(**{k: h[k] for k in Graded.model_fields}) for h in human], judge)
        close = sum(
            all(abs(getattr(j, f) - int(h[f])) <= 1 for f in ("faithful", "correct", "clear"))
            for j, h in zip(judged, human, strict=False)
        )
        agreement = close / len(judged) if judged else None

    summary = {
        "date": date.today().isoformat(),
        "sha": git_sha(),
        "judge_model": settings.judge_model,
        "prompt_version": load_prompt("judge").version,
        "reasons_graded": len(flat),
        "mean": {f: round(mean(flat, f), 2) for f in ("faithful", "correct", "clear")},
        "share_4_or_more": {
            f: round(sum(getattr(g, f) >= 4 for g in flat) / max(len(flat), 1), 3)
            for f in ("faithful", "correct", "clear")
        },
        "controls": {"pairs": len(good_grades), "judge_preferred_real_reason": wins},
        "human_labels": len(human),
        "human_agreement_within_1": agreement,
        "validated_against_humans": bool(
            agreement is not None and len(human) >= 20 and agreement >= 0.8
        ),
    }
    (REPORTS / "judge.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Reason quality (LLM-as-judge)",
        "",
        f"{summary['date']}, git `{summary['sha']}`, judge `{settings.judge_model}` (prompt v{summary['prompt_version']}), {len(flat)} reasons from the full suite.",
        "",
        "| Scale | Mean (1-5) | Scored 4 or 5 |",
        "|---|---|---|",
        *[
            f"| {f} | {summary['mean'][f]} | {summary['share_4_or_more'][f]:.1%} |"
            for f in ("faithful", "correct", "clear")
        ],
        "",
        "## Is the judge trustworthy?",
        "",
        f"- Synthetic controls: the judge scored the real reason above a reason swapped in from a different-verdict item in **{wins} of {len(good_grades)}** pairs.",
        f"- Human labels: **{len(human)} of 20** (`data/judge_labels.json`; fill in faithful/correct/clear, 1-5)."
        + (
            f" Agreement within one point on all three scales: **{agreement:.0%}**."
            if agreement is not None
            else ""
        )
        + " EVALS.md requires 80% agreement on 20 labels before these scores are trusted"
        + (
            "; that bar is met."
            if summary["validated_against_humans"]
            else "; until then they are reported as unvalidated."
        ),
    ]
    (REPORTS / "judge.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
