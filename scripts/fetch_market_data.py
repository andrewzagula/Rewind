"""Download real daily OHLCV history and register it as Rewind datasets.

Run inside the backend container so the database and data volume are reachable:

    docker compose exec backend python scripts/fetch_market_data.py AAPL SPY TSLA MSFT GOOG
    docker compose exec backend python scripts/fetch_market_data.py NVDA --start 2015-01-01

Data comes from free, key-less providers (Stooq first, then Yahoo Finance). Files are written
under data/market and registered in the datasets table, replacing any earlier fetch for the
same symbol.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for candidate in (ROOT / "backend", ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

DEFAULT_SYMBOLS = ["AAPL", "SPY", "TSLA", "MSFT", "GOOG"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "symbols", nargs="*", default=DEFAULT_SYMBOLS, help="Ticker symbols to fetch"
    )
    parser.add_argument(
        "--start", type=date.fromisoformat, default=None, help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end", type=date.fromisoformat, default=None, help="End date (YYYY-MM-DD)"
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()

    from app.core.database import async_session
    from app.services import market_data_service

    failures = 0
    async with async_session() as db:
        for symbol in args.symbols:
            try:
                dataset = await market_data_service.fetch_and_register(
                    db, symbol, args.start, args.end
                )
            except market_data_service.MarketDataError as exc:
                failures += 1
                print(f"  {symbol}: FAILED - {exc}")
                continue
            print(
                f"  {dataset.symbols[0]}: {dataset.row_count} bars "
                f"{dataset.start_date} -> {dataset.end_date} "
                f"from {dataset.source} -> {dataset.file_path}"
            )

    print("Done." if failures == 0 else f"Done with {failures} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
