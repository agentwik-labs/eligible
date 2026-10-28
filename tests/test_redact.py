from pathlib import Path

import pytest

from eligible.models import GoldenReceipt
from eligible.redact import redact

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.parametrize(
    "card", ["4111111111111111", "4111 1111 1111 1111", "5555-5555-5555-4444", "378282246310005"]
)
def test_luhn_valid_card_numbers_are_masked(card: str) -> None:
    out = redact(f"CARD {card}\nTOTAL 9.99")
    assert out.text == "CARD [CARD]\nTOTAL 9.99"
    assert out.counts == {"card_number": 1}


@pytest.mark.parametrize(
    "text",
    [
        "ORDER 4111111111111112",  # 16 digits, fails Luhn
        "VISA ************7246",  # already masked by the store
        "RX 4419023 ATORVASTATIN",  # prescription number
        "SUBTOTAL 1,688.72",
        "D2392 RESIN 2SURF POST 210.00",
    ],
)
def test_ordinary_numbers_survive(text: str) -> None:
    assert redact(text).text == text


@pytest.mark.parametrize("phone", ["(321) 555-0147", "407-555-0163", "407.555.0163"])
def test_phone_numbers_are_masked(phone: str) -> None:
    assert redact(f"RX PICKUP PH: {phone}").text == "RX PICKUP PH: [PHONE]"


def test_emails_and_labelled_names_are_masked() -> None:
    out = redact("PATIENT: TESTY MCTESTFACE\nE-RECEIPT SENT TO shopper12@example.com\nname: Jo")
    assert out.text == "PATIENT: [NAME]\nE-RECEIPT SENT TO [EMAIL]\nname: [NAME]"
    assert out.counts == {"email": 1, "patient_name": 2}


def test_no_personal_data_from_the_golden_set_survives_redaction() -> None:
    leaks = []
    for path in sorted((DATA / "golden").glob("r*.json")):
        golden = GoldenReceipt.model_validate_json(path.read_text())
        text = redact((DATA / "receipts" / f"{golden.receipt_id}.txt").read_text()).text
        leaks += [(golden.receipt_id, p.value) for p in golden.pii if p.value in text]
    assert leaks == []
