from decimal import Decimal

from eligible.decide import Decision
from eligible.models import FieldConfidence, LineItem
from eligible.retrieve.chunk import Chunk
from eligible.validate import canonical, validate_item


def chunk(cid: str) -> Chunk:
    return Chunk(id=cid, source_id=cid.split("#")[0], doc="p502", heading_path=["X"], text="t")


def item(conf: float = 0.99) -> LineItem:
    c = FieldConfidence(name=conf, quantity=0.99, unit_price=0.99, amount=0.99)
    return LineItem(
        raw_text="GAUZE",
        name="gauze pads",
        quantity=1,
        unit_price=Decimal(1),
        amount=Decimal(1),
        confidence=c,
    )


RETRIEVED = [chunk("elist:bandages#0"), chunk("p502:bandages#0")]


def test_citation_without_chunk_suffix_resolves_only_to_a_retrieved_source() -> None:
    assert canonical("elist:bandages", RETRIEVED) == "elist:bandages#0"
    assert canonical("p502:bandages#0", RETRIEVED) == "p502:bandages#0"
    assert canonical("elist:crutches", RETRIEVED) is None
    assert canonical("p502:bandages#3", RETRIEVED) is None


def test_unretrieved_citation_is_removed_and_verdict_needs_support() -> None:
    d = Decision(index=0, verdict="eligible", reason="ok", citation_ids=["p969:other#0"])
    result, bad = validate_item(item(), d, RETRIEVED)
    assert bad == 1
    assert result.verdict == "needs_review"
    assert "no_supporting_source" in result.flags


def test_supported_verdict_survives_and_low_confidence_goes_to_review() -> None:
    d = Decision(index=0, verdict="eligible", reason="ok", citation_ids=["elist:bandages"])
    result, bad = validate_item(item(), d, RETRIEVED)
    assert (result.verdict, bad, [c.chunk_id for c in result.citations]) == (
        "eligible",
        0,
        ["elist:bandages#0"],
    )
    low, _ = validate_item(item(conf=0.3), d, RETRIEVED)
    assert low.verdict == "needs_review"
    assert "low_confidence" in low.flags
