"""Request/response models for every LLM call. One shape for live, cached and replayed calls."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Effort = Literal["low", "medium", "high", "xhigh", "max"]
Source = Literal["api", "cache"]


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]


class LLMRequest(BaseModel):
    """Everything that determines a model's output. Its hash is the cache and fixture key."""

    model_config = ConfigDict(frozen=True)

    model: str
    prompt_name: str
    prompt_version: str
    # Static instructions only. This is the cached prefix, so anything per-request
    # (dates, IDs, retrieved chunks) belongs in `messages`, never here.
    system: str
    messages: list[Message]
    max_tokens: int = 4096
    effort: Effort | None = None
    output_schema: dict[str, Any] | None = None
    cache_system: bool = True

    def cache_key(self) -> str:
        return _sha256(self.model_dump(mode="json"))

    def system_hash(self) -> str:
        return _sha256(self.system)[:12]


class Usage(BaseModel):
    input_tokens: int = 0  # uncached input, billed at the base rate
    output_tokens: int = 0  # includes thinking tokens
    thinking_tokens: int = 0  # subset of output_tokens
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        """Total prompt size: the API splits it across three fields."""
        return (
            self.input_tokens
            + self.cache_read_tokens
            + self.cache_write_5m_tokens
            + self.cache_write_1h_tokens
        )


class LLMResponse(BaseModel):
    request_key: str
    prompt_name: str
    prompt_version: str
    system_hash: str
    model: str
    text: str
    stop_reason: str | None
    usage: Usage
    cost_usd: Decimal  # what this call actually cost (0 when served from the local cache)
    avoided_cost_usd: Decimal = Decimal(0)  # original cost of a response replayed from cache
    latency_ms: float
    source: Source = "api"
    effort: Effort | None = None

    def json_output(self) -> Any:
        """Parse structured output. Refuses to parse a truncated or refused response."""
        if self.stop_reason != "end_turn":
            raise IncompleteResponseError(self)
        return json.loads(self.text)


class IncompleteResponseError(RuntimeError):
    def __init__(self, response: LLMResponse) -> None:
        super().__init__(
            f"{response.prompt_name}@{response.prompt_version} stopped with "
            f"{response.stop_reason!r}; output is not usable"
        )
        self.response = response


class TokenBreakdown(BaseModel):
    """Dollar cost per token class, for reports."""

    input: Decimal = Field(default=Decimal(0))
    output: Decimal = Field(default=Decimal(0))
    cache_read: Decimal = Field(default=Decimal(0))
    cache_write: Decimal = Field(default=Decimal(0))

    @property
    def total(self) -> Decimal:
        return self.input + self.output + self.cache_read + self.cache_write


def _sha256(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
