from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from eligible.llm.types import LLMRequest, Message


def make_request(**overrides: Any) -> LLMRequest:
    fields: dict[str, Any] = {
        "model": "claude-sonnet-5-5",
        "prompt_name": "smoke",
        "prompt_version": "1",
        "system": "You classify receipt items. Reply with JSON.",
        "messages": [Message(role="user", content="IBUPRF 200MG 50CT 8.99")],
        "max_tokens": 512,
        "effort": "low",
    }
    fields.update(overrides)
    return LLMRequest(**fields)


class FakeMessages:
    """Stands in for `anthropic.Anthropic().messages`; records what it was sent."""

    def __init__(self, text: str, stop_reason: str = "end_turn", **usage: int) -> None:
        self.calls: list[dict[str, Any]] = []
        self._text = text
        self._stop_reason = stop_reason
        self._usage = {
            "input_tokens": 120,
            "output_tokens": 40,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            **usage,
        }

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        u = self._usage
        return SimpleNamespace(
            model=kwargs["model"],
            stop_reason=self._stop_reason,
            content=[SimpleNamespace(type="text", text=self._text)],
            usage=SimpleNamespace(
                input_tokens=u["input_tokens"],
                output_tokens=u["output_tokens"],
                cache_read_input_tokens=u["cache_read_input_tokens"],
                cache_creation_input_tokens=u["cache_creation_input_tokens"],
                cache_creation=SimpleNamespace(
                    ephemeral_5m_input_tokens=u["cache_creation_input_tokens"],
                    ephemeral_1h_input_tokens=0,
                ),
                output_tokens_details=SimpleNamespace(thinking_tokens=u.get("thinking", 0)),
            ),
        )


@pytest.fixture
def request_() -> LLMRequest:
    return make_request()
