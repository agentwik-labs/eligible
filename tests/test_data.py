import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest
from data.generate import MERCHANT_COUNTS, SEED, VERDICT_WEIGHTS, generate

from eligible.knowledge.eligibility import load_list
from eligible.knowledge.sources import load_sections
from eligible.models import GoldenReceipt

DATA = Path(__file__).resolve().parents[1] / "data"
RECEIPTS = sorted(
    (GoldenReceipt.model_validate_json(p.read_text()) for p in (DATA / "golden").glob("r*.json")),
    key=lambda r: r.receipt_id,
)


def luhn_ok(number: str) -> bool:
    digits = [int(d) for d in reversed(number)]
    total = sum(digits[0::2]) + sum(sum(divmod(2 * d, 10)) for d in digits[1::2])
    return total % 10 == 0


def test_sixty_receipts_each_with_text_image_and_label() -> None:
    assert len(RECEIPTS) == 60
    for r in RECEIPTS:
        assert (DATA / "receipts" / f"{r.receipt_id}.txt").exists()
        assert (DATA / "receipts" / f"{r.receipt_id}.png").exists()
        assert 3 <= len(r.items) <= 12


def test_verdict_distribution_matches_data_md() -> None:
    items = [i for r in RECEIPTS for i in r.items]
    shares = Counter(i.verdict for i in items)
    for verdict, target in VERDICT_WEIGHTS.items():
        assert abs(shares[verdict] / len(items) - target) <= 0.02, verdict


def test_merchant_mix_matches_data_md() -> None:
    assert Counter(r.merchant_type for r in RECEIPTS) == Counter(MERCHANT_COUNTS)


def test_totals_add_up_and_mismatches_are_labelled() -> None:
    assert sum(r.totals_mismatch for r in RECEIPTS) == 6
    for r in RECEIPTS:
        line_sum = sum((i.amount for i in r.items), Decimal(0))
        assert r.total == r.subtotal_printed + r.tax
        assert r.totals_mismatch == (abs(line_sum - r.subtotal_printed) > Decimal("0.02"))
        assert all(i.amount == i.unit_price * i.quantity for i in r.items)


def test_labels_point_at_real_list_entries_and_sections() -> None:
    entries = {e.source_id: e for e in load_list()}
    sections = load_sections()
    for r in RECEIPTS:
        for item in r.items:
            entry = entries[item.gold_source_ids[0]]
            assert item.verdict == entry.verdict
            assert all(s in sections for s in item.gold_source_ids[1:])


def test_receipt_text_contains_every_item_and_all_pii_is_fake() -> None:
    for r in RECEIPTS:
        text = (DATA / "receipts" / f"{r.receipt_id}.txt").read_text()
        assert all(i.raw_text[:28] in text for i in r.items)
        for p in r.pii:
            assert p.value in text
            if p.kind == "card_number":
                assert luhn_ok(p.value)
            if p.kind == "phone":
                assert re.fullmatch(r"\(\d{3}\) 555-01\d\d", p.value)
            if p.kind == "email":
                assert p.value.endswith("@example.com")
    kinds = Counter(p.kind for r in RECEIPTS for p in r.pii)
    assert set(kinds) == {"card_number", "phone", "email", "patient_name"}


@pytest.mark.parametrize("seed", [SEED])
def test_dataset_regenerates_byte_for_byte_from_its_seed(tmp_path: Path, seed: int) -> None:
    generate(seed, out=tmp_path, images=False)
    for path in (DATA / "golden").glob("r*.json"):
        assert (tmp_path / "golden" / path.name).read_text() == path.read_text()
    for path in (DATA / "receipts").glob("r*.txt"):
        assert (tmp_path / "receipts" / path.name).read_text() == path.read_text()
    assert json.loads((DATA / "golden" / "r0001.json").read_text())["seed"] == seed
