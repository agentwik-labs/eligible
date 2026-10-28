import pytest

from eligible.demo import main


def test_demo_runs_offline_and_flags_the_cache_bust(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    out = capsys.readouterr().out
    assert "stopped after" in out
    assert "spent $0.0000 on the rerun" in out
    assert "decide@2-bug" in out
    assert "⚠" in out
