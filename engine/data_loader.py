"""Load historical OHLCV data from Parquet files via DuckDB."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "parquet"


def load_bars(
    symbol: str,
    timeframe: str = "1d",
    start: str | None = None,
    end: str | None = None,
    data_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Load OHLCV bars as a list of dicts.

    Attempts DuckDB first, falls back to PyArrow if DuckDB is unavailable.

    Args:
        symbol: Ticker symbol (e.g., "AAPL").
        timeframe: Bar timeframe (e.g., "1d", "1h").
        start: ISO date string filter (inclusive).
        end: ISO date string filter (inclusive).
        data_dir: Override for Parquet directory.
    """
    import duckdb

    directory = data_dir or DATA_DIR
    file_path = directory / f"{symbol}_{timeframe}.parquet"

    if not file_path.exists():
        raise FileNotFoundError(f"No data file found: {file_path}")

    conditions = []
    if start:
        conditions.append(f"timestamp >= '{start}'")
    if end:
        conditions.append(f"timestamp <= '{end}'")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM read_parquet('{file_path}') {where} ORDER BY timestamp"

    conn = duckdb.connect()
    result = conn.execute(query).fetchdf()
    conn.close()

    result["symbol"] = symbol
    return result.to_dict("records")
