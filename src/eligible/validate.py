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


def canonical(citation_id: str, retrieved: list[Chunk]) -> str | None:
    """The retrieved chunk a citation refers to, or None if it wasn't retrieved for this item.

    Models sometimes drop the chunk suffix ("elist:bandages" for "elist:bandages#0"). That
    still names a source retrieved for this item, so it resolves to that source's first chunk.
    A source that wasn't retrieved for the item never resolves.
    """
    for chunk in retrieved:
        if chunk.id == citation_id:
            return chunk.id
    for chunk in retrieved:
        if chunk.source_id == citation_id:
            return chunk.id
    return None


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
    resolved = [canonical(cid, retrieved) for cid in decision.citation_ids]
    unsupported = [cid for cid, r in zip(decision.citation_ids, resolved, strict=True) if r is None]
    cited = list({r: by_id[r] for r in resolved if r is not None}.values())
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
