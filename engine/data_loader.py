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
    file_path: Path | None = None,
) -> list[dict[str, Any]]:
    import duckdb

    if file_path is None:
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
