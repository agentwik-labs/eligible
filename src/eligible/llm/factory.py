"""Build the client the app and evals use."""

from __future__ import annotations

from eligible.config import Settings
from eligible.llm.budget import Budget
from eligible.llm.client import AnthropicClient, LLMClient, MeteredClient, ReplayClient
from eligible.llm.ledger import Ledger


def build_client(settings: Settings) -> MeteredClient:
    """The client the app and evals use: real API behind cache, budget and ledger."""
    inner: LLMClient
    if settings.llm_mode == "replay":
        inner = ReplayClient(settings.llm_cache_dir)
    elif settings.llm_mode == "record":
        inner = ReplayClient(settings.llm_cache_dir, inner=AnthropicClient())
    else:
        inner = AnthropicClient()
    return MeteredClient(inner, Budget(settings.budget_usd), Ledger(settings.ledger_path))
