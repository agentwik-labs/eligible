"""Eligible as MCP tools (SPEC §4): `uv run python -m eligible.mcp_server` (stdio).

Every call is logged to logs/mcp_calls.jsonl with its latency and model cost, so the
engineering page can show how the tools perform in practice.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from eligible.models import CheckResult, ItemResult
from eligible.pipeline import Checker
from eligible.retrieve.chunk import Chunk

CALL_LOG = Path(__file__).resolve().parents[2] / "logs" / "mcp_calls.jsonl"

server = MCPServer(
    "eligible",
    instructions=(
        "Checks whether an FSA or HSA can pay for receipt items, citing IRS sources. "
        "Use check_item for a single product or service, check_receipt for a whole receipt, "
        "and search_rules to read the rules themselves. Results are informational, not tax advice."
    ),
)


class Rule(BaseModel):
    chunk_id: str
    source_id: str
    title: str
    text: str


@cache
def checker() -> Checker:
    return Checker()


def log_call(tool: str, started: float, cost: Decimal, detail: str) -> None:
    CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CALL_LOG.open("a") as f:
        f.write(
            json.dumps(
                {
                    "time": datetime.now(UTC).isoformat(timespec="seconds"),
                    "tool": tool,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                    "cost_usd": str(cost),
                    "detail": detail,
                }
            )
            + "\n"
        )


@server.tool()
def check_receipt(text: str) -> CheckResult:
    """Check every line of a receipt (pasted as text): verdict, reason and IRS citations."""
    started = time.perf_counter()
    result = checker().check(text)
    log_call("check_receipt", started, result.cost_usd, f"{len(result.items)} items")
    return result


@server.tool()
def check_item(name: str) -> ItemResult:
    """Check one product or service by name, e.g. "sunscreen SPF 50" or "60 minute massage"."""
    started = time.perf_counter()
    result, response = checker().check_item(name)
    log_call("check_item", started, response.cost_usd, f"{name}: {result.verdict}")
    return result


@server.tool()
def search_rules(query: str, k: int = 5) -> list[Rule]:
    """Search the IRS sources and eligibility rules; returns the matching passages with IDs."""
    started = time.perf_counter()
    chunks: list[Chunk] = checker().retriever.search(query, k=min(max(k, 1), 10))
    log_call("search_rules", started, Decimal(0), f"{query}: {len(chunks)} passages")
    return [
        Rule(chunk_id=c.id, source_id=c.source_id, title=" > ".join(c.heading_path), text=c.text)
        for c in chunks
    ]


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
