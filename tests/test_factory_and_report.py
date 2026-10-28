from decimal import Decimal
from pathlib import Path

import pytest

from eligible.config import Settings
from eligible.llm.client import FixtureMissingError
from eligible.llm.factory import build_client
from eligible.llm.ledger import Ledger
from eligible.llm.report import main
from tests.conftest import make_request

FIXTURES = Path(__file__).parent / "fixtures" / "llm"


def test_replay_mode_serves_fixtures_and_logs_them(tmp_path: Path) -> None:
    ledger_path = tmp_path / "calls.jsonl"
    client = build_client(
        Settings(llm_mode="replay", llm_cache_dir=FIXTURES, ledger_path=ledger_path)
    )
    response = client.complete(make_request())
    assert response.source == "cache"
    assert client.budget.spent_usd == 0
    assert len(Ledger(ledger_path).read()) == 1


def test_replay_mode_never_reaches_the_network(tmp_path: Path) -> None:
    client = build_client(Settings(llm_mode="replay", llm_cache_dir=tmp_path))
    with pytest.raises(FixtureMissingError):
        client.complete(make_request())


def test_budget_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    client = build_client(Settings(llm_mode="live", budget_usd=Decimal("2.5")))
    assert client.budget.limit_usd == Decimal("2.5")


def test_report_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger_path = tmp_path / "calls.jsonl"
    assert main([str(ledger_path)]) == 0
    assert "no LLM calls" in capsys.readouterr().out
    build_client(
        Settings(llm_mode="replay", llm_cache_dir=FIXTURES, ledger_path=ledger_path)
    ).complete(make_request())
    main([str(ledger_path)])
    assert "Avoided by local response cache" in capsys.readouterr().out
