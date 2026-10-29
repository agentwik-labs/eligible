"""Domain types shared by the pipeline, the data generator and the evals."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["eligible", "not_eligible", "needs_prescription", "dual_purpose", "needs_review"]
VERDICTS: tuple[Verdict, ...] = (
    "eligible",
    "not_eligible",
    "dual_purpose",
    "needs_prescription",
    "needs_review",
)
MerchantType = Literal[
    "pharmacy", "grocery", "medical_provider", "optical", "dental", "big_box", "other"
]
PIIKind = Literal["card_number", "phone", "email", "patient_name"]


class GoldenItem(BaseModel):
    raw_text: str  # the line as printed, for matching extraction output
    name: str  # normalized name
    quantity: int = 1
    unit_price: Decimal
    amount: Decimal
    verdict: Verdict
    gold_source_ids: list[str] = Field(min_length=1)
    note: str


class PII(BaseModel):
    kind: PIIKind
    value: str


class GoldenReceipt(BaseModel):
    receipt_id: str
    merchant: str
    merchant_type: MerchantType
    date: date
    items: list[GoldenItem] = Field(min_length=1)
    subtotal_printed: Decimal
    tax: Decimal
    total: Decimal
    totals_mismatch: bool
    pii: list[PII] = []
    seed: int


# Extraction output (SPEC §2.2). Every field gets a 0-1 confidence; < LOW_CONFIDENCE is flagged.
LOW_CONFIDENCE = 0.6


class FieldConfidence(BaseModel):
    name: float = Field(ge=0, le=1)
    quantity: float = Field(ge=0, le=1)
    unit_price: float = Field(ge=0, le=1)
    amount: float = Field(ge=0, le=1)


class LineItem(BaseModel):
    raw_text: str
    name: str
    quantity: int | None
    unit_price: Decimal | None
    amount: Decimal
    confidence: FieldConfidence

    def low_confidence_fields(self) -> list[str]:
        return [f for f, c in self.confidence.model_dump().items() if c < LOW_CONFIDENCE]


class Receipt(BaseModel):
    merchant: str | None
    merchant_type: MerchantType
    date: date | None
    items: list[LineItem]
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    read_quality: Literal["good", "partial", "poor"]


# Decision output (SPEC §2.5-2.6, §3).
class Citation(BaseModel):
    chunk_id: str
    source_id: str
    title: str  # heading path, e.g. "Pub 969 > Flexible Spending Arrangements > Distributions"
    quote: str


class ItemResult(BaseModel):
    item: LineItem
    verdict: Verdict
    reason: str
    citations: list[Citation]
    flags: list[str] = []  # why validation changed or questioned the verdict


class Stage(BaseModel):
    name: str
    ms: float
    cost_usd: Decimal = Decimal(0)
    prompt_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    replayed: bool = False  # served from the response cache, so it cost nothing this time
    detail: str = ""


class CheckResult(BaseModel):
    receipt: Receipt
    items: list[ItemResult]
    eligible_subtotal: Decimal
    totals_mismatch: bool
    needs_review_count: int
    trace_id: str
    cost_usd: Decimal
    latency_ms: float
    prompt_versions: dict[str, str]
    unsupported_citations_before_validation: int = 0
    stages: list[Stage] = []
