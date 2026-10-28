import json
from decimal import Decimal
from pathlib import Path

import pytest

from eligible.extract import RECEIPT_SCHEMA, build_request, extract
from eligible.llm.types import LLMRequest, LLMResponse, Usage
from eligible.prompts import load_prompt

DATA = Path(__file__).resolve().parents[1] / "data"
ITEM = {
    "raw_text": "IBUPRF 200MG 50CT",
    "name": "ibuprofen 200 mg, 50 count",
    "quantity": 1,
    "unit_price": 8.99,
    "amount": 8.99,
    "confidence": {"name": 0.97, "quantity": 0.99, "unit_price": 0.99, "amount": 0.99},
}
RECEIPT = {
    "merchant": "CORNER DRUG CO",
    "merchant_type": "pharmacy",
    "date": "2026-03-14",
    "items": [
        ITEM,
        {
            **ITEM,
            "raw_text": "HBA MISC",
            "name": "unidentified item",
            "confidence": {**ITEM["confidence"], "name": 0.3},
        },
    ],
    "subtotal": 17.98,
    "tax": 0.0,
    "total": 17.98,
    "read_quality": "good",
}


class FakeClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            request_key=request.cache_key(),
            prompt_name=request.prompt_name,
            prompt_version=request.prompt_version,
            system_hash=request.system_hash(),
            model=request.model,
            text=json.dumps(self.payload),
            stop_reason="end_turn",
            usage=Usage(input_tokens=10, output_tokens=10),
            cost_usd=Decimal("0.001"),
            latency_ms=1.0,
        )


def test_prompt_has_a_version_and_the_request_carries_it() -> None:
    request = build_request("RECEIPT")
    assert request.prompt_version == load_prompt("extract").version
    assert request.output_schema == RECEIPT_SCHEMA
    assert request.messages[0].content == "<receipt>\nRECEIPT</receipt>"


def test_extract_redacts_before_the_model_sees_anything() -> None:
    client = FakeClient(RECEIPT)
    text = (DATA / "receipts" / "r0007.txt").read_text()
    extraction = extract(text, client)
    sent = str(client.requests[0].messages[0].content)
    assert "[PHONE]" in sent
    assert "555-01" not in sent
    assert extraction.redaction.counts


def test_money_stays_exact_and_low_confidence_is_flagged() -> None:
    extraction = extract("text", FakeClient(RECEIPT))
    assert extraction.receipt.items[0].amount == Decimal("8.99")
    assert extraction.receipt.total == Decimal("17.98")
    assert extraction.flagged == [(1, "name")]


def test_schema_is_strict_everywhere() -> None:
    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                walk(value)

    walk(RECEIPT_SCHEMA)


def test_bad_front_matter_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import eligible.prompts as prompts

    (tmp_path / "broken.md").write_text("no header\n")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    prompts.load_prompt.cache_clear()
    with pytest.raises(ValueError, match="front-matter"):
        prompts.load_prompt("broken")
    prompts.load_prompt.cache_clear()
