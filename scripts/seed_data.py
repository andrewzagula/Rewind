"""Generate sample OHLCV data for development and testing."""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


def generate_ohlcv(
    symbol: str,
    start: str = "2020-01-01",
    end: str = "2024-12-31",
    initial_price: float = 100.0,
) -> pd.DataFrame:
    """Generate synthetic daily OHLCV data with random walk prices."""
    dates = pd.bdate_range(start=start, end=end)
    n = len(dates)

    rng = np.random.default_rng(hash(symbol) % 2**32)
    returns = rng.normal(0.0004, 0.02, n)
    close = initial_price * np.cumprod(1 + returns)

    high = close * (1 + rng.uniform(0, 0.03, n))
    low = close * (1 - rng.uniform(0, 0.03, n))
    open_ = low + (high - low) * rng.uniform(0.2, 0.8, n)
    volume = rng.integers(1_000_000, 50_000_000, n)

    return pd.DataFrame({
        "timestamp": dates,
        "open": np.round(open_, 2),
        "high": np.round(high, 2),
        "low": np.round(low, 2),
        "close": np.round(close, 2),
        "volume": volume,
    })


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    symbols = {"AAPL": 150.0, "SPY": 400.0, "TSLA": 200.0, "MSFT": 300.0, "GOOG": 130.0}

    for symbol, price in symbols.items():
        df = generate_ohlcv(symbol, initial_price=price)
        path = DATA_DIR / f"{symbol}_1d.parquet"
        df.to_parquet(path, index=False)
        print(f"  {symbol}: {len(df)} bars -> {path}")

    print("Sample data generated.")


if __name__ == "__main__":
    main()
