from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from eligible.llm.client import AnthropicClient, FixtureMissingError, ReplayClient
from tests.conftest import FakeMessages, make_request

FIXTURES = Path(__file__).parent / "fixtures" / "llm"


def recording(tmp_path: Path, fake: FakeMessages) -> ReplayClient:
    sdk: Any = type("FakeSDK", (), {"messages": fake})()
    return ReplayClient(tmp_path, inner=AnthropicClient(sdk=cast(Any, sdk)))


def test_replay_without_fixture_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FixtureMissingError, match="ELIGIBLE_LLM_MODE=record"):
        ReplayClient(tmp_path).complete(make_request())


def test_second_identical_call_is_free(tmp_path: Path) -> None:
    fake = FakeMessages('{"ok": true}')
    client = recording(tmp_path, fake)
    first = client.complete(make_request())
    second = client.complete(make_request())
    assert len(fake.calls) == 1
    assert second.source == "cache"
    assert second.cost_usd == 0
    assert second.avoided_cost_usd == first.cost_usd > Decimal(0)
    assert second.text == first.text


def test_prompt_version_bump_invalidates_cache(tmp_path: Path) -> None:
    fake = FakeMessages('{"ok": true}')
    client = recording(tmp_path, fake)
    client.complete(make_request(prompt_version="1"))
    client.complete(make_request(prompt_version="2"))
    assert len(fake.calls) == 2


def test_failed_responses_are_not_cached(tmp_path: Path) -> None:
    fake = FakeMessages("{", stop_reason="max_tokens")
    client = recording(tmp_path, fake)
    client.complete(make_request())
    client.complete(make_request())
    assert len(fake.calls) == 2


def test_committed_fixture_replays_offline() -> None:
    """Also pins the cache-key format: if hashing changes, every eval cache entry is lost."""
    response = ReplayClient(FIXTURES).complete(make_request())
    assert response.json_output() == {
        "name": "ibuprofen 200 mg, 50 count",
        "verdict": "eligible",
    }
    assert response.source == "cache"
