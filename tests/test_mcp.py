import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest

import eligible.mcp_server as mcp_server
from eligible.llm.types import LLMResponse, Usage
from eligible.models import FieldConfidence, ItemResult, LineItem
from eligible.retrieve.chunk import Chunk


class FakeRetriever:
    def search(self, query: str, k: int = 5) -> list[Chunk]:
        return [
            Chunk(
                id="elist:sunscreen#0",
                source_id="elist:sunscreen",
                doc="elist",
                heading_path=["Eligibility list", "sunscreen"],
                text="Verdict: dual_purpose.",
            )
        ][:k]


class FakeChecker:
    retriever = FakeRetriever()

    def check_item(self, name: str) -> tuple[ItemResult, LLMResponse]:
        conf = FieldConfidence(name=1, quantity=1, unit_price=1, amount=1)
        item = LineItem(
            raw_text=name,
            name=name,
            quantity=1,
            unit_price=None,
            amount=Decimal(0),
            confidence=conf,
        )
        result = ItemResult(
            item=item, verdict="dual_purpose", reason="Medical use only.", citations=[]
        )
        response = LLMResponse(
            request_key="k",
            prompt_name="decide",
            prompt_version="2",
            system_hash="s",
            model="claude-sonnet-5-5",
            text="{}",
            stop_reason="end_turn",
            usage=Usage(),
            cost_usd=Decimal("0.01"),
            latency_ms=1.0,
        )
        return result, response


@pytest.fixture(autouse=True)
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mcp_server, "checker", lambda: FakeChecker())
    monkeypatch.setattr(mcp_server, "CALL_LOG", tmp_path / "calls.jsonl")


def text_of(result: object) -> str:
    return result.content[0].text  # type: ignore[attr-defined]


def test_three_tools_with_descriptions() -> None:
    tools = asyncio.run(mcp_server.server.list_tools())
    assert {t.name for t in tools} == {"check_receipt", "check_item", "search_rules"}
    assert all(t.description for t in tools)


def test_check_item_returns_a_verdict_and_logs_the_call() -> None:
    result = asyncio.run(mcp_server.server.call_tool("check_item", {"name": "sunscreen"}))
    assert json.loads(text_of(result))["verdict"] == "dual_purpose"
    logged = json.loads(mcp_server.CALL_LOG.read_text().splitlines()[0])
    assert (logged["tool"], logged["cost_usd"]) == ("check_item", "0.01")


def test_search_rules_returns_passages_with_ids() -> None:
    result = asyncio.run(
        mcp_server.server.call_tool("search_rules", {"query": "sunscreen", "k": 1})
    )
    assert json.loads(text_of(result))["chunk_id"] == "elist:sunscreen#0"
