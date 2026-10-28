"""The only place in the codebase that talks to an LLM (CLAUDE.md rule 6).

Clients compose:

    MeteredClient(            budget guard + per-call ledger (cost, tokens, latency)
        ReplayClient(         response cache keyed by request hash; fixtures for tests
            AnthropicClient   the real API
        ))

Tests use ReplayClient with no inner client, so a missing fixture fails loudly
instead of calling the network.
"""

from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import anthropic

from eligible.llm import pricing
from eligible.llm.budget import Budget, estimate_max_cost_usd
from eligible.llm.ledger import Ledger
from eligible.llm.types import LLMRequest, LLMResponse, Usage


class LLMClient(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...


def build_params(request: LLMRequest) -> dict[str, Any]:
    """Translate an LLMRequest into Messages API arguments."""
    system_block: dict[str, Any] = {"type": "text", "text": request.system}
    if request.cache_system:
        system_block["cache_control"] = {"type": "ephemeral"}
    params: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "system": [system_block],
        "messages": [m.model_dump() for m in request.messages],
    }
    output_config: dict[str, Any] = {}
    if request.effort is not None:
        output_config["effort"] = request.effort
    if request.output_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": request.output_schema}
    if output_config:
        params["output_config"] = output_config
    return params


def usage_from_api(raw: Any) -> Usage:
    """Normalize the API's usage object, including the 5m/1h cache-write split."""
    created = getattr(raw, "cache_creation", None)
    write_5m = getattr(created, "ephemeral_5m_input_tokens", None)
    write_1h = getattr(created, "ephemeral_1h_input_tokens", None)
    if write_5m is None and write_1h is None:
        write_5m = getattr(raw, "cache_creation_input_tokens", 0) or 0
    details = getattr(raw, "output_tokens_details", None)
    return Usage(
        input_tokens=raw.input_tokens,
        output_tokens=raw.output_tokens,
        thinking_tokens=getattr(details, "thinking_tokens", 0) or 0,
        cache_read_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        cache_write_5m_tokens=write_5m or 0,
        cache_write_1h_tokens=write_1h or 0,
    )


class AnthropicClient:
    def __init__(self, sdk: anthropic.Anthropic | None = None) -> None:
        self._sdk = sdk or anthropic.Anthropic()

    def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        message = self._sdk.messages.create(**build_params(request))
        latency_ms = (time.perf_counter() - started) * 1000
        usage = usage_from_api(message.usage)
        text = "".join(block.text for block in message.content if block.type == "text")
        return LLMResponse(
            request_key=request.cache_key(),
            prompt_name=request.prompt_name,
            prompt_version=request.prompt_version,
            system_hash=request.system_hash(),
            model=message.model,
            text=text,
            stop_reason=message.stop_reason,
            usage=usage,
            cost_usd=pricing.cost_usd(request.model, usage),
            latency_ms=latency_ms,
            effort=request.effort,
        )


class FixtureMissingError(LookupError):
    pass


class ReplayClient:
    """Serves responses from disk by request hash.

    With `inner`, a miss calls through and records the response (eval cache, EVALS.md §5).
    Without it, a miss raises (unit tests: no network, ever).
    """

    def __init__(self, directory: Path, inner: LLMClient | None = None) -> None:
        self._dir = directory
        self._inner = inner

    def path_for(self, request: LLMRequest) -> Path:
        return self._dir / f"{request.prompt_name}-{request.cache_key()[:16]}.json"

    def complete(self, request: LLMRequest) -> LLMResponse:
        path = self.path_for(request)
        if path.exists():
            recorded = LLMResponse.model_validate_json(path.read_text())
            return recorded.model_copy(
                update={
                    "source": "cache",
                    "cost_usd": Decimal(0),
                    "avoided_cost_usd": recorded.cost_usd,
                    "latency_ms": 0.0,
                }
            )
        if self._inner is None:
            raise FixtureMissingError(
                f"no recorded response at {path}. Record it with ELIGIBLE_LLM_MODE=record."
            )
        response = self._inner.complete(request)
        if response.stop_reason == "end_turn":  # never cache a truncated or refused answer
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(response.model_dump_json(indent=2))
        return response


class MeteredClient:
    """Enforces a spend ceiling before each call and logs every call to the ledger."""

    def __init__(self, inner: LLMClient, budget: Budget, ledger: Ledger | None = None) -> None:
        self._inner = inner
        self.budget = budget
        self._ledger = ledger

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.budget.check(estimate_max_cost_usd(request))
        response = self._inner.complete(request)
        self.budget.charge(response.cost_usd)
        if self._ledger is not None:
            self._ledger.append(response)
        return response
