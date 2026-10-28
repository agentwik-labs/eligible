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
