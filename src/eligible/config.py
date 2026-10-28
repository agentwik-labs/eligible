"""Settings from the environment (and `.env`). Every model ID is configurable."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from eligible.llm.types import Effort

LLMMode = Literal["live", "record", "replay"]
LLMBackend = Literal["auto", "anthropic_api", "claude_code"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ELIGIBLE_", env_file=".env", extra="ignore")

    extract_model: str = "claude-sonnet-5-5"
    decide_model: str = "claude-sonnet-5-5"
    judge_model: str = "claude-haiku-5-5"
    effort: Effort = "low"

    # live: call the API. record: serve from the response cache, call the API on a miss.
    # replay: cache only, a miss is an error (unit tests).
    llm_mode: LLMMode = "record"
    # auto: the Anthropic API when ANTHROPIC_API_KEY is set, otherwise the Claude Code CLI.
    llm_backend: LLMBackend = "auto"
    llm_cache_dir: Path = Path("evals/.cache")
    budget_usd: Decimal = Decimal("10")
    ledger_path: Path = Path("logs/llm_calls.jsonl")


@lru_cache
def get_settings() -> Settings:
    return Settings()
