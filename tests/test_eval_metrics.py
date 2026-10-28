from decimal import Decimal

from evals.metrics import detect_mismatch, match_items, score_receipt, summarize

from eligible.models import FieldConfidence, GoldenItem, GoldenReceipt, LineItem, Receipt

CONF = FieldConfidence(name=0.99, quantity=0.99, unit_price=0.99, amount=0.99)


def golden_item(text: str, amount: str, verdict: str = "eligible") -> GoldenItem:
    return GoldenItem(
        raw_text=text,
        name=text.lower(),
        unit_price=Decimal(amount),
        amount=Decimal(amount),
        verdict=verdict,
        gold_source_ids=["elist:x"],
        note="",
    )


def line(text: str, amount: str, name_conf: float = 0.99) -> LineItem:
    return LineItem(
        raw_text=text,
        name=text.lower(),
        quantity=1,
        unit_price=Decimal(amount),
        amount=Decimal(amount),
        confidence=CONF.model_copy(update={"name": name_conf}),
    )


def test_matching_is_one_to_one_and_survives_small_typos() -> None:
    golden = [golden_item("IBUPRF 200MG 50CT", "8.99"), golden_item("BAND AID FLX 30CT", "4.99")]
    extracted = [
        line("IBUPRF 200MG 50 CT", "8.99"),
        line("BANDAID FLX 30CT", "5.99"),
        line("CANDY", "1"),
    ]
    pairs = match_items(golden, extracted)
    assert len(pairs) == 2
    assert {e.raw_text for _, e in pairs} == {"IBUPRF 200MG 50 CT", "BANDAID FLX 30CT"}


def test_mismatch_detection_uses_two_cent_tolerance() -> None:
    def receipt(subtotal: str) -> Receipt:
        return Receipt(
            merchant="M",
            merchant_type="pharmacy",
            date=None,
            items=[line("A", "1.00"), line("B", "2.00")],
            subtotal=Decimal(subtotal),
            tax=None,
            total=None,
            read_quality="good",
        )

    assert not detect_mismatch(receipt("3.02"))
    assert detect_mismatch(receipt("4.00"))


def test_summary_counts_recall_amount_errors_and_unreadable_flags() -> None:
    golden = GoldenReceipt(
        receipt_id="r1",
        merchant="CORNER DRUG CO",
        merchant_type="pharmacy",
        date="2026-03-14",
        items=[
            golden_item("IBUPRF 200MG 50CT", "8.99"),
            golden_item("HBA MISC", "7.99", "needs_review"),
            golden_item("TOOTHPASTE 4OZ", "3.99", "not_eligible"),
        ],
        subtotal_printed=Decimal("20.97"),
        tax=Decimal(0),
        total=Decimal("20.97"),
        totals_mismatch=False,
        seed=1,
    )
    extracted = Receipt(
        merchant="CORNER DRUG CO",
        merchant_type="pharmacy",
        date=golden.date,
        items=[line("IBUPRF 200MG 50CT", "9.99"), line("HBA MISC", "7.99", name_conf=0.2)],
        subtotal=Decimal("20.97"),
        tax=Decimal(0),
        total=Decimal("20.97"),
        read_quality="good",
    )
    s = summarize([score_receipt(golden, extracted, "redacted text with no personal data")])
    assert round(s.item_recall, 3) == 0.667
    assert s.item_precision == 1.0
    assert s.amount_exact == 0.5
    assert s.unreadable_flagged == (1, 1)
    assert s.readable_flagged == (0, 1)
    assert s.pii_leaks == 0
