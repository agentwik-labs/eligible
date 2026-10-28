"""LLMClient backed by the Claude Code CLI (`claude -p`), for running without an API key.

It uses the signed-in Claude login instead of ANTHROPIC_API_KEY. Each call replaces Claude
Code's system prompt with ours, disables every tool and MCP server, and runs in an empty
directory so no CLAUDE.md or settings leak into the prompt. The CLI reports the same usage
fields as the API, so pricing, caching stats and the ledger work unchanged.

Limits compared with the API backend: one user turn of plain text (no images), and
`max_tokens` is not enforced by the CLI (the budget guard still assumes it).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from eligible.llm import pricing
from eligible.llm.types import LLMRequest, LLMResponse, Usage

Runner = Callable[[Sequence[str], str, Path], str]


class ClaudeCodeError(RuntimeError):
    pass


def _run(cmd: Sequence[str], stdin: str, cwd: Path) -> str:
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        list(cmd), input=stdin, cwd=cwd, capture_output=True, text=True, timeout=600, check=False
    )
    if done.returncode != 0 and not done.stdout.strip():
        raise ClaudeCodeError(f"claude exited {done.returncode}: {done.stderr.strip()[:500]}")
    return done.stdout


def build_command(request: LLMRequest, executable: str = "claude") -> list[str]:
    cmd = [
        executable,
        "-p",
        "--model",
        request.model,
        "--system-prompt",
        request.system,
        "--tools",
        "",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--no-session-persistence",
        "--output-format",
        "json",
    ]
    if request.effort is not None:
        cmd += ["--effort", request.effort]
    if request.output_schema is not None:
        cmd += ["--json-schema", json.dumps(request.output_schema, separators=(",", ":"))]
    return cmd


def prompt_text(request: LLMRequest) -> str:
    if len(request.messages) != 1 or request.messages[0].role != "user":
        raise ValueError("the Claude Code backend sends exactly one user message")
    content = request.messages[0].content
    if isinstance(content, str):
        return content
    if any(block.get("type") != "text" for block in content):
        raise ValueError("the Claude Code backend accepts text only, not images")
    return "\n".join(str(block["text"]) for block in content)


def usage_from_cli(raw: dict[str, Any]) -> Usage:
    created = raw.get("cache_creation") or {}
    write_5m = created.get("ephemeral_5m_input_tokens")
    write_1h = created.get("ephemeral_1h_input_tokens")
    if write_5m is None and write_1h is None:
        write_5m = raw.get("cache_creation_input_tokens", 0)
    details = raw.get("output_tokens_details") or {}
    return Usage(
        input_tokens=raw.get("input_tokens", 0),
        output_tokens=raw.get("output_tokens", 0),
        thinking_tokens=details.get("thinking_tokens", 0) or 0,
        cache_read_tokens=raw.get("cache_read_input_tokens", 0) or 0,
        cache_write_5m_tokens=write_5m or 0,
        cache_write_1h_tokens=write_1h or 0,
    )


class ClaudeCodeClient:
    def __init__(self, runner: Runner = _run, executable: str | None = None) -> None:
        self._runner = runner
        self._executable = executable or shutil.which("claude") or "claude"
        self._cwd = Path(tempfile.mkdtemp(prefix="eligible-claude-"))

    def complete(self, request: LLMRequest) -> LLMResponse:
        out = self._runner(
            build_command(request, self._executable), prompt_text(request), self._cwd
        )
        result = json.loads(out)
        if result.get("is_error"):
            raise ClaudeCodeError(f"{result.get('subtype')}: {str(result.get('result'))[:500]}")
        usage = usage_from_cli(result.get("usage", {}))
        structured = result.get("structured_output")
        completed = result.get("terminal_reason") == "completed"
        text = json.dumps(structured) if structured is not None else str(result.get("result", ""))
        return LLMResponse(
            request_key=request.cache_key(),
            prompt_name=request.prompt_name,
            prompt_version=request.prompt_version,
            system_hash=request.system_hash(),
            model=request.model,
            text=text,
            stop_reason="end_turn" if completed else str(result.get("terminal_reason")),
            usage=usage,
            cost_usd=pricing.cost_usd(request.model, usage),
            latency_ms=float(result.get("duration_ms", 0)),
            effort=request.effort,
        )
