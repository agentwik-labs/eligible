import json
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pytest

from eligible.config import Settings
from eligible.llm.claude_code import ClaudeCodeClient, ClaudeCodeError, build_command
from eligible.llm.factory import backend_name
from eligible.llm.types import Message
from tests.conftest import make_request

# Shape copied from a real `claude -p --output-format json` result (trimmed).
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "duration_ms": 1573,
    "result": '{"word":"ok"}',
    "structured_output": {"word": "ok"},
    "usage": {
        "input_tokens": 2,
        "cache_creation_input_tokens": 1157,
        "cache_read_input_tokens": 0,
        "output_tokens": 52,
        "output_tokens_details": {"thinking_tokens": 0},
        "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 1157},
    },
    "total_cost_usd": 0.0002576,
}


class FakeRunner:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, cmd: Sequence[str], stdin: str, cwd: Path) -> str:
        self.calls.append((list(cmd), stdin))
        return json.dumps(self.result)


def test_command_replaces_system_prompt_and_disables_tools() -> None:
    cmd = build_command(make_request(output_schema={"type": "object"}))
    assert cmd[cmd.index("--system-prompt") + 1].startswith("You classify")
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--effort") + 1] == "low"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == {"type": "object"}


def test_cost_matches_what_claude_code_reports() -> None:
    runner = FakeRunner(RESULT)
    response = ClaudeCodeClient(runner=runner).complete(make_request(model="claude-haiku-5-5"))
    assert runner.calls[0][1] == "IBUPRF 200MG 50CT 8.99"  # the prompt goes over stdin
    assert response.json_output() == {"word": "ok"}
    assert response.usage.cache_write_1h_tokens == 1157
    assert abs(response.cost_usd - Decimal(str(RESULT["total_cost_usd"]))) < Decimal("0.000001")


def test_errors_raise_and_images_are_refused() -> None:
    failing = FakeRunner({**RESULT, "is_error": True, "subtype": "error_max_turns"})
    with pytest.raises(ClaudeCodeError, match="error_max_turns"):
        ClaudeCodeClient(runner=failing).complete(make_request())
    image = [{"type": "image", "source": {}}]
    with pytest.raises(ValueError, match="text only"):
        ClaudeCodeClient(runner=FakeRunner(RESULT)).complete(
            make_request(messages=[Message(role="user", content=image)])
        )


def test_incomplete_run_is_not_parsed() -> None:
    runner = FakeRunner({**RESULT, "terminal_reason": "max_turns"})
    response = ClaudeCodeClient(runner=runner).complete(make_request())
    assert response.stop_reason == "max_turns"


def test_auto_backend_picks_api_only_when_a_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert backend_name(Settings()) == "claude_code"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert backend_name(Settings()) == "anthropic_api"
    assert backend_name(Settings(llm_backend="claude_code")) == "claude_code"
