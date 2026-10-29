"""Deterministic checks on the model's verdicts (SPEC §2.6). No LLM here."""

from __future__ import annotations

from decimal import Decimal

from eligible.decide import Decision
from eligible.models import Citation, ItemResult, LineItem, Receipt
from eligible.retrieve.chunk import Chunk

TOLERANCE = Decimal("0.02")


def quote(chunk: Chunk, limit: int = 280) -> str:
    text = " ".join(chunk.text.split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def validate_item(
    item: LineItem, decision: Decision | None, retrieved: list[Chunk]
) -> tuple[ItemResult, int]:
    """Returns the checked result and how many citations weren't among the retrieved chunks."""
    if decision is None:
        return ItemResult(
            item=item,
            verdict="needs_review",
            reason="No decision was returned for this item.",
            citations=[],
            flags=["missing_decision"],
        ), 0
    by_id = {c.id: c for c in retrieved}
    unsupported = [cid for cid in decision.citation_ids if cid not in by_id]
    cited = [by_id[cid] for cid in decision.citation_ids if cid in by_id]
    citations = [
        Citation(
            chunk_id=c.id, source_id=c.source_id, title=" > ".join(c.heading_path), quote=quote(c)
        )
        for c in cited
    ]
    verdict, reason, flags = decision.verdict, decision.reason, []
    if unsupported:
        flags.append("unsupported_citation")
    if not citations and verdict != "needs_review":
        verdict, reason = "needs_review", "No supporting source."
        flags.append("no_supporting_source")
    low = item.low_confidence_fields()
    if low and verdict != "not_eligible":
        verdict = "needs_review"
        reason = f"The receipt line couldn't be read with confidence ({', '.join(low)}). {reason}"
        flags.append("low_confidence")
    return ItemResult(
        item=item, verdict=verdict, reason=reason, citations=citations, flags=flags
    ), len(unsupported)


def totals_mismatch(receipt: Receipt) -> bool:
    if receipt.subtotal is None:
        return False
    return abs(sum((i.amount for i in receipt.items), Decimal(0)) - receipt.subtotal) > TOLERANCE


def validate(
    receipt: Receipt, decisions: list[Decision], retrieved: list[list[Chunk]]
) -> tuple[list[ItemResult], int]:
    by_index = {d.index: d for d in decisions}
    results, unsupported = [], 0
    for i, (item, chunks) in enumerate(zip(receipt.items, retrieved, strict=True)):
        result, bad = validate_item(item, by_index.get(i), chunks)
        results.append(result)
        unsupported += bad
    return results, unsupported
