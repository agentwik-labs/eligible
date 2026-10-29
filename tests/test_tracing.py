from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import eligible.api as api
from eligible.models import CheckResult, Receipt, Stage
from eligible.tracing import Tracer


def result(trace_id: str) -> CheckResult:
    receipt = Receipt(
        merchant="M",
        merchant_type="pharmacy",
        date=None,
        items=[],
        subtotal=None,
        tax=None,
        total=None,
        read_quality="good",
    )
    spans = [
        Stage(
            name="extract",
            start_ms=0,
            ms=900,
            model="claude-haiku-5-5",
            prompt_tokens=100,
            output_tokens=50,
            cost_usd=Decimal("0.001"),
        ),
        Stage(name="retrieve", start_ms=900, ms=20),
        Stage(name="retrieve: gauze", parent="retrieve", start_ms=900, ms=10),
    ]
    return CheckResult(
        receipt=receipt,
        items=[],
        eligible_subtotal=Decimal(0),
        totals_mismatch=False,
        needs_review_count=0,
        trace_id=trace_id,
        cost_usd=Decimal("0.001"),
        latency_ms=920,
        prompt_versions={"extract": "1"},
        stages=spans,
    )


def test_traces_are_appended_and_read_newest_first(tmp_path: Path) -> None:
    tracer = Tracer(tmp_path / "traces.jsonl")
    tracer.record(result("a"))
    tracer.record(result("b"))
    recent = tracer.recent()
    assert [t.trace_id for t in recent] == ["b", "a"]
    assert recent[0].spans[2].parent == "retrieve"
    assert recent[0].spans[0].model == "claude-haiku-5-5"


def test_a_broken_trace_sink_never_breaks_a_check(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    Tracer(blocker / "traces.jsonl").record(result("c"))  # logs the error, doesn't raise


def test_traces_api_and_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = Tracer(tmp_path / "traces.jsonl")
    tracer.record(result("z"))

    class FakeChecker:
        pass

    fake = FakeChecker()
    fake.tracer = tracer  # type: ignore[attr-defined]
    monkeypatch.setattr(api, "checker", lambda: fake)
    client = TestClient(api.app)
    assert client.get("/v1/traces").json()[0]["trace_id"] == "z"
    assert "span by span" in client.get("/traces").text
