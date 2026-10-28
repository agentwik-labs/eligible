from eligible.llm.projection import Scenario, render, stages


def test_projection_covers_every_priced_model() -> None:
    table = render(Scenario())
    for model in ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"):
        assert model in table


def test_haiku_is_cheaper_than_sonnet_per_receipt() -> None:
    def total(model: str) -> float:
        return float(sum(c.cost_usd for c in stages(Scenario(), model)))

    assert total("claude-haiku-5-5") < total("claude-sonnet-5-5") / 10
