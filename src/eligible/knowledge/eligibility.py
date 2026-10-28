"""The hand-written eligibility list (data/knowledge/eligibility_list.yaml)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from eligible.models import MerchantType, Verdict

LIST_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "eligibility_list.yaml"


class Product(BaseModel):
    receipt_text: str
    name: str
    price: Decimal
    merchants: list[MerchantType] | None = None  # overrides the entry's merchants


class Entry(BaseModel):
    id: str
    names: list[str] = Field(min_length=1)
    verdict: Verdict
    rule: str = Field(min_length=10)
    sources: list[str] = Field(min_length=1)
    merchants: list[MerchantType] = Field(min_length=1)
    products: list[Product] = Field(min_length=1)

    @field_validator("products", mode="before")
    @classmethod
    def _from_triples(cls, value: list[object]) -> list[object]:
        return [
            dict(zip(("receipt_text", "name", "price", "merchants"), v, strict=False))
            if isinstance(v, list)
            else v
            for v in value
        ]

    def sold_at(self, merchant: MerchantType) -> list[Product]:
        return [p for p in self.products if merchant in (p.merchants or self.merchants)]

    @property
    def source_id(self) -> str:
        return f"elist:{self.id}"


def load_list(path: Path = LIST_PATH) -> list[Entry]:
    return [Entry.model_validate(raw) for raw in yaml.safe_load(path.read_text())]
