"""Build docs/devlog.json: how Eligible was built, from real records only.

    uv run python scripts/devlog.py [--session PATH_TO_CLAUDE_CODE_SESSION.jsonl ...]

Sources:
- git history: commits, lines changed, and test count at each commit;
- evals/.cache/: one file per real model call the product made (prompt, tokens, cost);
- Claude Code session logs (optional): token usage of the AI pair-programmer that built it.
  Only per-hour aggregates are written: no prompts, messages or file contents.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from eligible.llm import pricing
from eligible.llm.types import LLMResponse, Usage

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "devlog.json"
GIT = shutil.which("git") or "git"
MILESTONE = re.compile(r"\b(M\d)\b")


def git(*args: str) -> str:
    return subprocess.run([GIT, *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout  # noqa: S603


def hour(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:00Z")


def commits() -> list[dict[str, Any]]:
    out = []
    log = git("log", "--reverse", "--format=%x1e%H%x1f%cI%x1f%s", "--numstat")
    for block in log.split("\x1e")[1:]:
        head, *stat = block.strip("\n").split("\n")
        sha, when, subject = head.split("\x1f")
        added = removed = 0
        for line in stat:
            parts = line.split("\t")
            if len(parts) == 3 and parts[0].isdigit() and parts[2].endswith(".py"):
                added, removed = added + int(parts[0]), removed + int(parts[1])
        tests = (
            sum(
                int(n)
                for n in re.findall(
                    r":(\d+)$", git("grep", "-c", "def test_", sha, "--", "tests").strip(), re.M
                )
            )
            if "tests" in git("ls-tree", "--name-only", sha)
            else 0
        )
        match = MILESTONE.search(subject)
        out.append(
            {
                "sha": sha[:7],
                "time": when,
                "subject": subject,
                "milestone": match[1] if match else None,
                "py_added": added,
                "py_removed": removed,
                "tests": tests,
            }
        )
    return out


def product_spend() -> dict[str, Any]:
    by_prompt: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "prompt_tokens": 0,
            "output_tokens": 0,
            "cache_read": 0,
            "cost": Decimal(0),
        }
    )
    by_hour: dict[str, Decimal] = defaultdict(Decimal)
    for path in sorted((ROOT / "evals" / ".cache").glob("*.json")):
        r = LLMResponse.model_validate_json(path.read_text())
        key = f"{r.prompt_name}@{r.prompt_version} · {r.model}"
        row = by_prompt[key]
        row["calls"] += 1
        row["prompt_tokens"] += r.usage.prompt_tokens
        row["output_tokens"] += r.usage.output_tokens
        row["cache_read"] += r.usage.cache_read_tokens
        row["cost"] += r.cost_usd
        by_hour[hour(datetime.fromtimestamp(path.stat().st_mtime, UTC))] += r.cost_usd
    total = sum((row["cost"] for row in by_prompt.values()), Decimal(0))
    return {
        "note": "Every distinct model call the product made, read from the response cache. "
        "API-equivalent cost; reruns of unchanged cases were served from the cache at $0.",
        "calls": sum(row["calls"] for row in by_prompt.values()),
        "cost_usd": total,
        "by_prompt": [{"prompt": k, **v} for k, v in sorted(by_prompt.items())],
        "by_hour": [{"hour": h, "cost_usd": c} for h, c in sorted(by_hour.items())],
    }


def session_spend(paths: list[Path]) -> dict[str, Any] | None:
    if not paths:
        return None
    seen: set[str] = set()
    per_hour: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    tokens: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    models: Counter[str] = Counter()
    turns = 0
    for path in paths:
        for line in path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = entry.get("message")
            if entry.get("type") != "assistant" or not isinstance(message, dict):
                continue
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools[str(block.get("name", "?")).split("__")[-1]] += 1
            msg_id, raw = message.get("id"), message.get("usage")
            if not raw or msg_id in seen:
                continue
            seen.add(msg_id)
            turns += 1
            model = message.get("model", "")
            models[model] += 1
            created = raw.get("cache_creation") or {}
            usage = Usage(
                input_tokens=raw.get("input_tokens", 0),
                output_tokens=raw.get("output_tokens", 0),
                cache_read_tokens=raw.get("cache_read_input_tokens", 0),
                cache_write_5m_tokens=created.get("ephemeral_5m_input_tokens", 0),
                cache_write_1h_tokens=created.get("ephemeral_1h_input_tokens", 0),
            )
            if model not in pricing.PRICES:
                continue
            p = pricing.breakdown(model, usage)
            bucket = per_hour[
                hour(datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")))
            ]
            bucket["cache_read"] += p.cache_read
            bucket["cache_write"] += p.cache_write
            bucket["output"] += p.output
            bucket["input"] += p.input
            tokens["input"] += usage.input_tokens
            tokens["output"] += usage.output_tokens
            tokens["cache_read"] += usage.cache_read_tokens
            tokens["cache_write"] += usage.cache_write_5m_tokens + usage.cache_write_1h_tokens
    total = sum((sum(b.values(), Decimal(0)) for b in per_hour.values()), Decimal(0))
    prompt = tokens["input"] + tokens["cache_read"] + tokens["cache_write"]
    return {
        "note": "Claude Code building this repo: per-hour API-equivalent cost by token class, "
        "priced with llm/pricing.py. Aggregates only.",
        "model_turns": turns,
        "models": dict(models),
        "tokens": dict(tokens),
        "cache_read_share": tokens["cache_read"] / prompt if prompt else 0,
        "cost_usd": total,
        "tool_calls": dict(tools.most_common(12)),
        "by_hour": [
            {"hour": h, **{k: v for k, v in b.items()}} for h, b in sorted(per_hour.items())
        ],
    }


CAUGHT = [
    {
        "what": "Retrieval couldn't link products to the law",
        "caught_by": "retrieval ablation (eval)",
        "before": "recall@5 52.8%, OTC rule found 0%",
        "after": "recall@5 93.8%, OTC rule found 97.8%",
        "fix": "citation expansion from list entries to the IRS sections they cite",
        "evidence": "evals/reports/retrieval-ablation.md",
    },
    {
        "what": "The model invented citations",
        "caught_by": "decision eval",
        "before": "28 of 945 citations weren't among the retrieved sources",
        "after": "0 reached a user",
        "fix": "deterministic validation removes them and routes unsupported verdicts to review",
        "evidence": "evals/reports/latest.md",
    },
    {
        "what": "A budget overrun wouldn't stop an eval run",
        "caught_by": "checking the production-concerns claims against code",
        "before": "per-receipt error handler swallowed BudgetExceededError",
        "after": "the run halts; tests/test_eval_run.py proves it",
        "fix": "re-raise the budget error, never fall back to a cheaper model",
        "evidence": "tests/test_eval_run.py",
    },
    {
        "what": "Receipt file upload was broken",
        "caught_by": "API tests",
        "before": "every multipart upload rejected",
        "after": "uploads work",
        "fix": "add python-multipart; check Starlette's UploadFile type",
        "evidence": "tests/test_api.py",
    },
    {
        "what": "The decide prompt was too short to cache",
        "caught_by": "cost report (prompt-cache read share)",
        "before": "15.5% of prompt tokens from cache; decide 1.5x its projection",
        "after": "open: M5 lever",
        "fix": "planned: move stable rule text into the cached prefix, shorten chunks",
        "evidence": "evals/reports/latest.md",
    },
    {
        "what": "Synthetic data was skewed and repetitive",
        "caught_by": "distribution test and the 20-receipt audit",
        "before": "needs_prescription 4% vs 10% target; one grab bar on 5 of 20 receipts",
        "after": "every class within 1 point; no product more than 7 times in 441 items",
        "fix": "verdict quota across all item slots; more products per rule",
        "evidence": "data/golden/AUDIT.md",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    payload = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "commits": commits(),
        "product_spend": product_spend(),
        "build_session": session_spend(args.session) if args.session else None,
        "caught": CAUGHT,
    }
    OUT.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
