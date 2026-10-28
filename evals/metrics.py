"""Extraction metrics (EVALS.md §2.1). Pure functions over golden and extracted receipts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher

from eligible.models import GoldenItem, GoldenReceipt, LineItem, Receipt

MATCH_THRESHOLD = 0.6
BUCKETS = [(0.0, 0.6), (0.6, 0.8), (0.8, 0.95), (0.95, 1.01)]


def _norm(text: str) -> str:
    return " ".join(text.upper().split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def match_items(
    golden: list[GoldenItem], extracted: list[LineItem]
) -> list[tuple[GoldenItem, LineItem]]:
    """Greedy one-to-one matching on printed text, so a wrong amount still counts as a match
    (it shows up in amount accuracy instead of hiding as a missed item)."""
    pairs = sorted(
        (
            (similarity(g.raw_text, e.raw_text), gi, ei)
            for gi, g in enumerate(golden)
            for ei, e in enumerate(extracted)
        ),
        reverse=True,
    )
    used_g: set[int] = set()
    used_e: set[int] = set()
    matched = []
    for score, gi, ei in pairs:
        if score < MATCH_THRESHOLD or gi in used_g or ei in used_e:
            continue
        used_g.add(gi)
        used_e.add(ei)
        matched.append((golden[gi], extracted[ei]))
    return matched


@dataclass
class ReceiptScore:
    receipt_id: str
    golden_items: int
    extracted_items: int
    matched: list[tuple[GoldenItem, LineItem]]
    merchant_ok: bool
    merchant_type_ok: bool
    date_ok: bool
    total_ok: bool
    mismatch_expected: bool
    mismatch_detected: bool
    pii_leaks: list[str] = field(default_factory=list)

    @property
    def amount_errors(self) -> list[tuple[GoldenItem, LineItem]]:
        return [(g, e) for g, e in self.matched if e.amount != g.amount]

    @property
    def missed(self) -> int:
        return self.golden_items - len(self.matched)

    @property
    def spurious(self) -> int:
        return self.extracted_items - len(self.matched)


def detect_mismatch(receipt: Receipt) -> bool:
    if receipt.subtotal is None:
        return False
    lines = sum((i.amount for i in receipt.items), Decimal(0))
    return abs(lines - receipt.subtotal) > Decimal("0.02")


def score_receipt(golden: GoldenReceipt, extracted: Receipt, sent_text: str) -> ReceiptScore:
    return ReceiptScore(
        receipt_id=golden.receipt_id,
        golden_items=len(golden.items),
        extracted_items=len(extracted.items),
        matched=match_items(golden.items, extracted.items),
        merchant_ok=similarity(golden.merchant, extracted.merchant or "") >= 0.9,
        merchant_type_ok=golden.merchant_type == extracted.merchant_type,
        date_ok=golden.date == extracted.date,
        total_ok=extracted.total is not None and extracted.total == golden.total,
        mismatch_expected=golden.totals_mismatch,
        mismatch_detected=detect_mismatch(extracted),
        pii_leaks=[p.kind for p in golden.pii if p.value in sent_text],
    )


@dataclass
class Summary:
    receipts: int
    item_recall: float
    item_precision: float
    amount_exact: float
    quantity_exact: float
    merchant_acc: float
    merchant_type_acc: float
    date_acc: float
    total_acc: float
    mismatch_recall: float
    mismatch_false_alarms: int
    pii_leaks: int
    flagged_fields: int
    unreadable_flagged: tuple[int, int]  # needs_review items whose name was flagged / all of them
    readable_flagged: tuple[int, int]  # every other item whose name was flagged / all of them
    calibration: list[tuple[str, int, float]]


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def summarize(scores: list[ReceiptScore]) -> Summary:
    matched = [pair for s in scores for pair in s.matched]
    golden_total = sum(s.golden_items for s in scores)
    extracted_total = sum(s.extracted_items for s in scores)
    calibration = []
    for lo, hi in BUCKETS:
        in_bucket = [(g, e) for g, e in matched if lo <= e.confidence.amount < hi]
        correct = sum(e.amount == g.amount for g, e in in_bucket)
        label = f"{lo:.2f}-{min(hi, 1.0):.2f}"
        calibration.append((label, len(in_bucket), _rate(correct, len(in_bucket))))
    expected = [s for s in scores if s.mismatch_expected]
    return Summary(
        receipts=len(scores),
        item_recall=_rate(len(matched), golden_total),
        item_precision=_rate(len(matched), extracted_total),
        amount_exact=_rate(sum(e.amount == g.amount for g, e in matched), len(matched)),
        quantity_exact=_rate(
            sum((e.quantity or 1) == g.quantity for g, e in matched), len(matched)
        ),
        merchant_acc=_rate(sum(s.merchant_ok for s in scores), len(scores)),
        merchant_type_acc=_rate(sum(s.merchant_type_ok for s in scores), len(scores)),
        date_acc=_rate(sum(s.date_ok for s in scores), len(scores)),
        total_acc=_rate(sum(s.total_ok for s in scores), len(scores)),
        mismatch_recall=_rate(sum(s.mismatch_detected for s in expected), len(expected)),
        mismatch_false_alarms=sum(s.mismatch_detected and not s.mismatch_expected for s in scores),
        pii_leaks=sum(len(s.pii_leaks) for s in scores),
        flagged_fields=sum(len(e.low_confidence_fields()) for _, e in matched),
        unreadable_flagged=_name_flags(matched, unreadable=True),
        readable_flagged=_name_flags(matched, unreadable=False),
        calibration=calibration,
    )


def _name_flags(matched: list[tuple[GoldenItem, LineItem]], unreadable: bool) -> tuple[int, int]:
    group = [e for g, e in matched if (g.verdict == "needs_review") == unreadable]
    return sum("name" in e.low_confidence_fields() for e in group), len(group)
