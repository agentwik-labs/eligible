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


def test_full_run_writes_reports_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole runner, from cases to Markdown and JSON reports, with a fake pipeline."""
    from decimal import Decimal

    from eligible.models import CheckResult, FieldConfidence, ItemResult, LineItem, Receipt

    class FakeChecker:
        def __init__(self, *args: object) -> None:
            pass

        def check(self, text: str) -> CheckResult:
            conf = FieldConfidence(name=0.99, quantity=0.99, unit_price=0.99, amount=0.99)
            items = [
                ItemResult(
                    item=LineItem(
                        raw_text=line[:24].strip(),
                        name="x",
                        quantity=1,
                        unit_price=Decimal(1),
                        amount=Decimal(1),
                        confidence=conf,
                    ),
                    verdict="eligible",
                    reason="r",
                    citations=[],
                )
                for line in text.splitlines()[5:7]
            ]
            receipt = Receipt(
                merchant="M",
                merchant_type="pharmacy",
                date=None,
                items=[i.item for i in items],
                subtotal=None,
                tax=None,
                total=None,
                read_quality="good",
            )
            return CheckResult(
                receipt=receipt,
                items=items,
                eligible_subtotal=Decimal(0),
                totals_mismatch=False,
                needs_review_count=0,
                trace_id="t" * 12,
                cost_usd=Decimal(0),
                latency_ms=1.0,
                prompt_versions={},
            )

    monkeypatch.setattr(run, "Checker", FakeChecker)
    monkeypatch.setattr(run, "build_client", lambda settings: None)
    monkeypatch.setattr(
        run,
        "get_settings",
        lambda: Settings(llm_cache_dir=tmp_path, ledger_path=tmp_path / "l.jsonl"),
    )
    monkeypatch.setattr(run, "REPORTS", tmp_path / "reports")
    for suite in ("smoke", "adversarial"):
        run.main(["--suite", suite, "--workers", "1"])
    names = {p.name for p in (tmp_path / "reports").iterdir()}
    assert "adversarial.json" in names
    assert any(n.endswith("-smoke.md") for n in names)
    assert "Injection-changed verdicts" in (tmp_path / "reports" / "adversarial.md").read_text()
