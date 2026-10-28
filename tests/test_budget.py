from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from eligible.llm.budget import (
    Budget,
    BudgetExceededError,
    estimate_input_tokens,
    estimate_max_cost_usd,
)
from eligible.llm.client import AnthropicClient, MeteredClient
from eligible.llm.ledger import Ledger
from eligible.llm.types import Message
from tests.conftest import FakeMessages, make_request


def metered(fake: FakeMessages, limit: str, ledger: Ledger | None = None) -> MeteredClient:
    sdk: Any = type("FakeSDK", (), {"messages": fake})()
    return MeteredClient(AnthropicClient(sdk=cast(Any, sdk)), Budget(Decimal(limit)), ledger)


def test_estimate_counts_text_and_images() -> None:
    image = {"type": "image", "source": {"type": "base64", "data": "..."}}
    text_only = make_request(system="x" * 350, messages=[Message(role="user", content="")])
    with_image = make_request(
        system="x" * 350, messages=[Message(role="user", content=[image, {"type": "text"}])]
    )
    assert estimate_input_tokens(text_only) == 100
    assert estimate_input_tokens(with_image) == 1_700


def test_worst_case_assumes_full_output_and_no_cache() -> None:
    request = make_request(system="x" * 3_500, messages=[], max_tokens=1_000)
    # 1000 in at $2 + 1000 out at $10, per million
    assert estimate_max_cost_usd(request) == Decimal("0.012")


def test_call_that_could_cross_the_ceiling_never_runs() -> None:
    fake = FakeMessages("{}")
    client = metered(fake, "0.001")
    with pytest.raises(BudgetExceededError, match="budget"):
        client.complete(make_request(max_tokens=4_096))
    assert fake.calls == []


def test_spend_accumulates_and_every_call_is_logged(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "calls.jsonl")
    client = metered(FakeMessages("{}"), "1", ledger)
    client.complete(make_request())
    client.complete(make_request())
    assert client.budget.spent_usd == 2 * Decimal("0.00064")
    assert len(ledger.read()) == 2
