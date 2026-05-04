import json
from pathlib import Path

import pytest

from engine.executor import run_backtest
from engine.strategy_runner import load_strategy_class
from engine.strategy_validator import validate_strategy_code

SAMPLES_PATH = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "sample-strategies.json"
)


def _load_samples() -> list[dict]:
    return json.loads(SAMPLES_PATH.read_text())


def _sample_rows() -> list[dict]:
    closes = (
        [100.0 + index * 0.8 for index in range(30)]
        + [124.0 - index * 1.8 for index in range(25)]
        + [79.0 + index * 2.2 for index in range(45)]
    )
    return [
        {
            "symbol": "TEST",
            "timestamp": f"2024-01-{index + 1:02d}",
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": 1_000_000 + index,
        }
        for index, close in enumerate(closes)
    ]


@pytest.mark.parametrize("sample", _load_samples(), ids=lambda sample: sample["id"])
def test_sample_strategy_validates_loads_and_runs(sample: dict) -> None:
    validation = validate_strategy_code(sample["code"])
    assert validation.valid, validation.errors

    strategy_class = load_strategy_class(sample["code"])
    result = run_backtest(strategy_class(), _sample_rows(), params={})

    assert len(result.equity_curve) == len(_sample_rows())
    assert len(result.equity_points) == len(_sample_rows())
    assert result.metrics
