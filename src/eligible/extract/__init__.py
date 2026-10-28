"""Receipt text -> typed line items with per-field confidence (SPEC §2.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from eligible.config import get_settings
from eligible.llm.client import LLMClient
from eligible.llm.types import LLMRequest, LLMResponse, Message
from eligible.models import Receipt
from eligible.prompts import load_prompt
from eligible.redact import Redaction, redact

MONEY = {"type": ["number", "null"]}
CONFIDENCE = {"type": "number", "minimum": 0, "maximum": 1}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


ITEM_SCHEMA = _object(
    {
        "raw_text": {"type": "string"},
        "name": {"type": "string"},
        "quantity": {"type": ["integer", "null"]},
        "unit_price": MONEY,
        "amount": {"type": "number"},
        "confidence": _object(
            {
                "name": CONFIDENCE,
                "quantity": CONFIDENCE,
                "unit_price": CONFIDENCE,
                "amount": CONFIDENCE,
            }
        ),
    }
)
RECEIPT_SCHEMA = _object(
    {
        "merchant": {"type": ["string", "null"]},
        "merchant_type": {
            "type": "string",
            "enum": [
                "pharmacy",
                "grocery",
                "medical_provider",
                "optical",
                "dental",
                "big_box",
                "other",
            ],
        },
        "date": {"type": ["string", "null"]},
        "items": {"type": "array", "items": ITEM_SCHEMA},
        "subtotal": MONEY,
        "tax": MONEY,
        "total": MONEY,
        "read_quality": {"type": "string", "enum": ["good", "partial", "poor"]},
    }
)


class Extraction(BaseModel):
    receipt: Receipt
    redaction: Redaction
    request: LLMRequest
    response: LLMResponse

    @property
    def flagged(self) -> list[tuple[int, str]]:
        """(item index, field) for every field below the confidence floor."""
        return [
            (i, f)
            for i, item in enumerate(self.receipt.items)
            for f in item.low_confidence_fields()
        ]


def build_request(redacted_text: str, model: str | None = None) -> LLMRequest:
    prompt = load_prompt("extract")
    return LLMRequest(
        model=model or get_settings().extract_model,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        system=prompt.text,
        messages=[Message(role="user", content=f"<receipt>\n{redacted_text}</receipt>")],
        max_tokens=4096,
        effort=get_settings().effort,
        output_schema=RECEIPT_SCHEMA,
    )


def extract(text: str, client: LLMClient, model: str | None = None) -> Extraction:
    redaction = redact(text)
    request = build_request(redaction.text, model)
    response = client.complete(request)
    receipt = Receipt.model_validate(_money_as_text(response.json_output()))
    return Extraction(receipt=receipt, redaction=redaction, request=request, response=response)


def _money_as_text(data: dict[str, Any]) -> dict[str, Any]:
    """JSON numbers arrive as floats; go through str so 8.99 stays Decimal('8.99')."""
    for key in ("subtotal", "tax", "total"):
        if isinstance(data.get(key), float | int):
            data[key] = str(data[key])
    for item in data.get("items", []):
        for key in ("unit_price", "amount"):
            if isinstance(item.get(key), float | int):
                item[key] = str(item[key])
    return data
