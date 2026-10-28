"""Mask personal data before any LLM call (SPEC §2.1). Runs on text; images are never logged."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable

from pydantic import BaseModel

CARD_RUN = re.compile(r"(?<![\d*])(?:\d[ -]?){12,18}\d(?!\d)")
PHONE = re.compile(r"(?<!\d)(?:\(\d{3}\)\s?|\d{3}[-.\s])\d{3}[-.\s]\d{4}(?!\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LABELED_NAME = re.compile(r"(?im)^(\s*(?:patient|name)\s*:\s*)(\S.*?)\s*$")


class Redaction(BaseModel):
    text: str
    counts: dict[str, int]


def luhn_valid(digits: str) -> bool:
    nums = [int(d) for d in reversed(digits)]
    total = sum(nums[0::2]) + sum(sum(divmod(2 * d, 10)) for d in nums[1::2])
    return total % 10 == 0


def redact(text: str) -> Redaction:
    counts: Counter[str] = Counter()

    def card(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            counts["card_number"] += 1
            return "[CARD]"
        return match.group(0)

    def tag(kind: str, label: str) -> Callable[[re.Match[str]], str]:
        def sub(match: re.Match[str]) -> str:
            counts[kind] += 1
            return label

        return sub

    text = CARD_RUN.sub(card, text)
    text = EMAIL.sub(tag("email", "[EMAIL]"), text)
    text = PHONE.sub(tag("phone", "[PHONE]"), text)

    def name(match: re.Match[str]) -> str:
        counts["patient_name"] += 1
        return f"{match.group(1)}[NAME]"

    text = LABELED_NAME.sub(name, text)
    return Redaction(text=text, counts=dict(counts))
