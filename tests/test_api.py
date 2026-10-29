from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import eligible.api as api
from eligible.models import CheckResult, Receipt


class FakeChecker:
    def check(self, text: str) -> CheckResult:
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
        return CheckResult(
            receipt=receipt,
            items=[],
            eligible_subtotal=Decimal(0),
            totals_mismatch=False,
            needs_review_count=0,
            trace_id="t",
            cost_usd=Decimal("0.01"),
            latency_ms=1.0,
            prompt_versions={},
        )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(api, "checker", lambda: FakeChecker())
    return TestClient(api.app)


def test_check_accepts_json_and_text_files(client: TestClient) -> None:
    assert client.post("/v1/check", json={"text": "RECEIPT"}).json()["trace_id"] == "t"
    files = {"file": ("r.txt", b"RECEIPT", "text/plain")}
    assert client.post("/v1/check", files=files).status_code == 200


def test_check_rejects_bad_input_with_a_reason(client: TestClient) -> None:
    assert client.post("/v1/check", json={"text": "  "}).status_code == 422
    assert client.post("/v1/check", json={"nope": 1}).status_code == 422
    image = {"file": ("r.png", b"\x89PNG", "image/png")}
    response = client.post("/v1/check", files=image)
    assert response.status_code == 415
    assert "paste the receipt text" in response.json()["detail"]


def test_samples_and_page(client: TestClient) -> None:
    ids = client.get("/v1/samples").json()
    assert len(ids) == 60
    assert "SUBTOTAL" in client.get(f"/v1/samples/{ids[0]}").json()["text"]
    assert client.get("/v1/samples/..%2Fsecret").status_code == 404
    page = client.get("/")
    assert page.status_code == 200
    assert "Check receipt" in page.text
