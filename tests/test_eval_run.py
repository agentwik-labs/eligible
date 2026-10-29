from decimal import Decimal
from pathlib import Path

import evals.run as run
import pytest

from eligible.config import Settings
from eligible.llm.budget import Budget, BudgetExceededError
from eligible.llm.client import MeteredClient, ReplayClient
from tests.test_extract import RECEIPT, FakeClient


def test_budget_overrun_halts_the_whole_eval_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spend ceiling must stop the run, not be swallowed as a per-receipt error."""
    inner = FakeClient(RECEIPT)
    broke = MeteredClient(ReplayClient(tmp_path, inner=inner), Budget(Decimal("0.000001")))
    monkeypatch.setattr(run, "build_client", lambda settings: broke)
    monkeypatch.setattr(run, "get_settings", lambda: Settings(llm_cache_dir=tmp_path))
    monkeypatch.setattr(run, "REPORTS", tmp_path / "reports")
    with pytest.raises(BudgetExceededError):
        run.main(["--suite", "smoke", "--workers", "1"])
    assert inner.requests == []  # nothing was sent past the ceiling
