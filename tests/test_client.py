from decimal import Decimal
from typing import Any, cast

import pytest

from eligible.llm.client import AnthropicClient, build_params
from eligible.llm.types import IncompleteResponseError
from tests.conftest import FakeMessages, make_request


def client_with(fake: FakeMessages) -> AnthropicClient:
    sdk: Any = type("FakeSDK", (), {"messages": fake})()
    return AnthropicClient(sdk=cast(Any, sdk))


def test_system_prompt_is_the_cached_prefix() -> None:
    params = build_params(make_request())
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in str(params["messages"])  # volatile content stays uncached


def test_cache_can_be_turned_off_for_one_off_prompts() -> None:
    params = build_params(make_request(cache_system=False))
    assert "cache_control" not in params["system"][0]


def test_effort_and_schema_go_in_output_config() -> None:
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    params = build_params(make_request(output_schema=schema))
    assert params["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": schema},
    }
    assert "temperature" not in params  # rejected by the current API version


def test_response_carries_tokens_cost_and_latency() -> None:
    fake = FakeMessages(
        '{"verdict": "eligible"}',
        input_tokens=200,
        output_tokens=50,
        cache_read_input_tokens=2_000,
        cache_creation_input_tokens=0,
        thinking=20,
    )
    response = client_with(fake).complete(make_request())
    assert response.json_output() == {"verdict": "eligible"}
    assert response.usage.prompt_tokens == 2_200
    assert response.usage.thinking_tokens == 20
    # 200*$2 + 50*$10 + 2000*$0.20, per million
    assert response.cost_usd == Decimal("0.0013")
    assert response.latency_ms >= 0
    assert response.source == "api"


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_truncated_or_refused_output_is_never_parsed(stop_reason: str) -> None:
    fake = FakeMessages('{"verdict": "elig', stop_reason=stop_reason)
    response = client_with(fake).complete(make_request())
    assert response.cost_usd > 0  # still billed, still counted
    with pytest.raises(IncompleteResponseError):
        response.json_output()
