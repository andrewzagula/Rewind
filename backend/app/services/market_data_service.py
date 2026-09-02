"""Fetch real daily OHLCV bars from free, key-less providers and register them as datasets.

Providers are tried in order. Stooq serves plain CSV and Yahoo Finance serves JSON; both
work without an API key. Bars are normalized to the Parquet shape the engine already reads
(timestamp, open, high, low, close, volume) and registered in the datasets table so they
show up in the dataset selector and can be used by the worker.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dataset import Dataset

SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
BAR_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
DEFAULT_HISTORY_DAYS = 365 * 5
REQUEST_TIMEOUT_SECONDS = 30.0
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Rewind/0.1 local research client"
TIMEFRAME = "1d"


class MarketDataError(Exception):
    """Raised when market data cannot be fetched from any provider or is unusable."""


class MarketDataValidationError(MarketDataError):
    """Raised for invalid user input such as a malformed symbol or an inverted date range."""


@dataclass(frozen=True)
class FetchRequest:
    symbol: str
    start_date: date
    end_date: date


class MarketDataProvider(Protocol):
    name: str

    def url(self, request: FetchRequest) -> str: ...

    def parse(self, body: str, request: FetchRequest) -> pd.DataFrame: ...


def normalize_symbol(symbol: str) -> str:
    normalized = (symbol or "").strip().upper()
    if not SYMBOL_RE.match(normalized):
        raise MarketDataValidationError(
            "Symbol must be 1-15 characters using letters, digits, '.', or '-'."
        )
    return normalized


def build_fetch_request(
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
    today: date | None = None,
) -> FetchRequest:
    today = today or datetime.now(UTC).date()
    end = end_date or today
    start = start_date or (end - timedelta(days=DEFAULT_HISTORY_DAYS))
    if start > end:
        raise MarketDataValidationError("start_date must be on or before end_date.")
    if start > today:
        raise MarketDataValidationError("start_date cannot be in the future.")
    return FetchRequest(symbol=normalize_symbol(symbol), start_date=start, end_date=end)


class StooqProvider:
    name = "stooq"

    def url(self, request: FetchRequest) -> str:
        symbol = request.symbol.lower()
        if "." not in symbol:
            symbol = f"{symbol.replace('-', '.')}.us" if "-" in symbol else f"{symbol}.us"
        return (
            "https://stooq.com/q/d/l/"
            f"?s={symbol}&d1={request.start_date:%Y%m%d}&d2={request.end_date:%Y%m%d}&i=d"
        )

    def parse(self, body: str, request: FetchRequest) -> pd.DataFrame:
        text = body.strip()
        if not text or text.lower().startswith("no data") or "Date" not in text.splitlines()[0]:
            raise MarketDataError("Stooq returned no rows for this symbol and range.")
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for row in reader:
            try:
                rows.append(
                    {
                        "timestamp": row["Date"],
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume") or 0),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return pd.DataFrame(rows, columns=BAR_COLUMNS)


class YahooProvider:
    name = "yahoo"

    def url(self, request: FetchRequest) -> str:
        start = int(datetime.combine(request.start_date, datetime.min.time(), UTC).timestamp())
        # Yahoo's period2 is exclusive, so include the end date by adding a day.
        end = int(
            datetime.combine(
                request.end_date + timedelta(days=1), datetime.min.time(), UTC
            ).timestamp()
        )
        return (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{request.symbol}"
            f"?period1={start}&period2={end}&interval=1d&events=history"
        )

    def parse(self, body: str, request: FetchRequest) -> pd.DataFrame:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise MarketDataError("Yahoo Finance returned a non-JSON response.") from exc

        chart = payload.get("chart") or {}
        error = chart.get("error")
        if error:
            description = error.get("description") if isinstance(error, dict) else str(error)
            raise MarketDataError(f"Yahoo Finance error: {description}")

        results = chart.get("result") or []
        if not results:
            raise MarketDataError("Yahoo Finance returned no rows for this symbol and range.")

        result = results[0]
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        rows = []
        for index, stamp in enumerate(timestamps):
            values = {
                key: _index_or_none(quote.get(key), index)
                for key in ("open", "high", "low", "close", "volume")
            }
            if any(values[key] is None for key in ("open", "high", "low", "close")):
                continue
            rows.append(
                {
                    "timestamp": datetime.fromtimestamp(int(stamp), UTC).date().isoformat(),
                    "open": float(values["open"]),
                    "high": float(values["high"]),
                    "low": float(values["low"]),
                    "close": float(values["close"]),
                    "volume": float(values["volume"] or 0),
                }
            )
        return pd.DataFrame(rows, columns=BAR_COLUMNS)


PROVIDERS: dict[str, MarketDataProvider] = {
    StooqProvider.name: StooqProvider(),
    YahooProvider.name: YahooProvider(),
}


def provider_chain(preferred: str | None = None) -> list[MarketDataProvider]:
    preferred_name = (preferred or settings.market_data_provider or "stooq").strip().lower()
    ordered = [PROVIDERS[preferred_name]] if preferred_name in PROVIDERS else []
    ordered.extend(provider for name, provider in PROVIDERS.items() if name != preferred_name)
    return ordered


def normalize_bars(raw: pd.DataFrame, request: FetchRequest) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=BAR_COLUMNS)

    bars = raw.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], errors="coerce", utc=True).dt.tz_localize(
        None
    )
    bars = bars.dropna(subset=["timestamp", "open", "high", "low", "close"])
    bars = bars[
        (bars["timestamp"] >= pd.Timestamp(request.start_date))
        & (bars["timestamp"] <= pd.Timestamp(request.end_date))
    ]
    bars = bars.sort_values("timestamp").drop_duplicates(subset="timestamp", keep="last")
    bars["timestamp"] = bars["timestamp"].dt.normalize()
    for column in ("open", "high", "low", "close"):
        bars[column] = bars[column].astype("float64").round(6)
    bars["volume"] = bars["volume"].fillna(0).astype("int64")
    return bars[BAR_COLUMNS].reset_index(drop=True)


async def fetch_daily_bars(
    request: FetchRequest,
    client: httpx.AsyncClient | None = None,
    providers: list[MarketDataProvider] | None = None,
) -> tuple[pd.DataFrame, str]:
    """Return normalized bars and the provider name that supplied them."""
    providers = providers or provider_chain()
    failures: list[str] = []
    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )
    try:
        for provider in providers:
            try:
                response = await http.get(provider.url(request))
                response.raise_for_status()
                bars = normalize_bars(provider.parse(response.text, request), request)
            except (httpx.HTTPError, MarketDataError, ValueError) as exc:
                failures.append(f"{provider.name}: {exc}")
                continue
            if bars.empty:
                failures.append(f"{provider.name}: no bars inside the requested range")
                continue
            return bars, provider.name
    finally:
        if owns_client:
            await http.aclose()

    raise MarketDataError(
        f"Unable to fetch daily bars for {request.symbol}. " + "; ".join(failures)
    )


def repo_data_root() -> Path:
    current = Path(__file__).resolve()
    candidates = [Path.cwd(), Path.cwd().parent, current.parents[3]]
    if len(current.parents) > 4:
        candidates.append(current.parents[4])
    for candidate in candidates:
        if (candidate / "data").is_dir():
            return candidate
    return current.parents[3]


def market_data_dir() -> Path:
    configured = Path(settings.market_data_dir)
    if configured.is_absolute():
        return configured
    return repo_data_root() / configured


def dataset_file_name(symbol: str, timeframe: str = TIMEFRAME) -> str:
    return f"{symbol}_{timeframe}.parquet"


def write_dataset_file(symbol: str, bars: pd.DataFrame, directory: Path | None = None) -> Path:
    directory = directory or market_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / dataset_file_name(symbol)
    bars.to_parquet(path, index=False)
    return path


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stored_file_path(path: Path, root: Path | None = None) -> str:
    root = root or repo_data_root()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


async def register_dataset(
    db: AsyncSession,
    *,
    symbol: str,
    bars: pd.DataFrame,
    file_path: str,
    checksum: str,
    source: str,
    name: str | None = None,
) -> Dataset:
    """Create or refresh the dataset row that points at ``file_path``."""
    existing = await db.scalar(select(Dataset).where(Dataset.file_path == file_path))
    dataset = existing or Dataset(file_path=file_path)
    dataset.name = name or f"{symbol} Daily"
    dataset.symbols = [symbol]
    dataset.timeframe = TIMEFRAME
    dataset.start_date = bars["timestamp"].iloc[0].date()
    dataset.end_date = bars["timestamp"].iloc[-1].date()
    dataset.row_count = int(len(bars))
    dataset.checksum = checksum
    dataset.source = source
    if existing is None:
        db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def fetch_and_register(
    db: AsyncSession,
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
    client: httpx.AsyncClient | None = None,
) -> Dataset:
    request = build_fetch_request(symbol, start_date, end_date)
    bars, provider = await fetch_daily_bars(request, client=client)
    path = write_dataset_file(request.symbol, bars)
    return await register_dataset(
        db,
        symbol=request.symbol,
        bars=bars,
        file_path=stored_file_path(path),
        checksum=file_checksum(path),
        source=provider,
    )


def dataset_payload(dataset: Dataset) -> dict[str, Any]:
    return {
        "id": str(dataset.id),
        "name": dataset.name,
        "symbols": list(dataset.symbols or []),
        "timeframe": dataset.timeframe,
        "start_date": dataset.start_date.isoformat() if dataset.start_date else None,
        "end_date": dataset.end_date.isoformat() if dataset.end_date else None,
        "row_count": dataset.row_count,
        "source": getattr(dataset, "source", "") or "",
        "file_path": dataset.file_path,
    }


def _index_or_none(values: Any, index: int) -> Any:
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]
