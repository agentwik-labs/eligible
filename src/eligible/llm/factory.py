"""Build the client the app and evals use."""

from __future__ import annotations

import os

from eligible.config import Settings
from eligible.llm.budget import Budget
from eligible.llm.claude_code import ClaudeCodeClient
from eligible.llm.client import AnthropicClient, LLMClient, MeteredClient, ReplayClient
from eligible.llm.ledger import Ledger
from eligible.llm.types import LLMRequest, LLMResponse


def backend_name(settings: Settings) -> str:
    if settings.llm_backend != "auto":
        return settings.llm_backend
    return "anthropic_api" if os.environ.get("ANTHROPIC_API_KEY") else "claude_code"


class ModelUnavailableError(RuntimeError):
    """No way to reach a model: the request can only be served from the response cache."""


class UnavailableClient:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise ModelUnavailableError(self.reason)


def build_backend(settings: Settings) -> LLMClient:
    if backend_name(settings) == "anthropic_api":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return UnavailableClient(
                "No ANTHROPIC_API_KEY is set, so this server can only replay receipts it has "
                "already checked (the samples). Set the key to check new receipts."
            )
        return AnthropicClient()
    return ClaudeCodeClient()


def build_client(settings: Settings) -> MeteredClient:
    """The client the app and evals use: a backend behind cache, budget and ledger."""
    inner: LLMClient
    if settings.llm_mode == "replay":
        inner = ReplayClient(settings.llm_cache_dir)
    elif settings.llm_mode == "record":
        inner = ReplayClient(settings.llm_cache_dir, inner=build_backend(settings))
    else:
        inner = build_backend(settings)
    return MeteredClient(inner, Budget(settings.budget_usd), Ledger(settings.ledger_path))
