from pathlib import Path

import pandas as pd

from engine.data_loader import load_bars


def _write_bars(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "timestamp": "2024-01-02",
                "open": 101.0,
                "high": 102.0,
                "low": 100.0,
                "close": 101.5,
                "volume": 1000,
            },
            {
                "timestamp": "2024-01-01",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 900,
            },
        ]
    ).to_parquet(path, index=False)


def test_load_bars_accepts_explicit_file_path(tmp_path: Path) -> None:
    file_path = tmp_path / "custom.parquet"
    _write_bars(file_path)

    bars = load_bars("MSFT", file_path=file_path)

    assert [bar["symbol"] for bar in bars] == ["MSFT", "MSFT"]
    assert [str(bar["timestamp"])[:10] for bar in bars] == ["2024-01-01", "2024-01-02"]


def test_load_bars_keeps_symbol_timeframe_data_dir_contract(tmp_path: Path) -> None:
    file_path = tmp_path / "AAPL_1d.parquet"
    _write_bars(file_path)

    bars = load_bars("AAPL", "1d", data_dir=tmp_path)

    assert len(bars) == 2
    assert bars[0]["symbol"] == "AAPL"
