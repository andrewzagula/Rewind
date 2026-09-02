import json
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from app.services import market_data_service as svc

STOOQ_CSV = """Date,Open,High,Low,Close,Volume
2024-01-03,184.22,185.88,183.43,184.25,58414500
2024-01-02,187.15,188.44,183.89,185.64,82488700
2024-01-04,182.15,183.09,180.88,181.91,71983600
"""


def yahoo_body(timestamps: list[int], closes: list[float | None]) -> str:
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "timestamp": timestamps,
                        "indicators": {
                            "quote": [
                                {
                                    "open": [c if c is None else c - 1 for c in closes],
                                    "high": [c if c is None else c + 1 for c in closes],
                                    "low": [c if c is None else c - 2 for c in closes],
                                    "close": closes,
                                    "volume": [1000 for _ in closes],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
    )


def test_normalize_symbol_uppercases_and_rejects_garbage() -> None:
    assert svc.normalize_symbol(" aapl ") == "AAPL"
    assert svc.normalize_symbol("brk-b") == "BRK-B"
    with pytest.raises(svc.MarketDataValidationError):
        svc.normalize_symbol("bad symbol!")
    with pytest.raises(svc.MarketDataValidationError):
        svc.normalize_symbol("")


def test_build_fetch_request_defaults_to_five_years() -> None:
    request = svc.build_fetch_request("spy", today=date(2026, 9, 2))
    assert request.symbol == "SPY"
    assert request.end_date == date(2026, 9, 2)
    assert request.start_date == date(2021, 9, 3)


def test_build_fetch_request_rejects_inverted_range() -> None:
    with pytest.raises(svc.MarketDataValidationError):
        svc.build_fetch_request("SPY", date(2024, 1, 2), date(2023, 1, 1))


def test_stooq_parse_and_normalize_sorts_and_filters() -> None:
    request = svc.FetchRequest("AAPL", date(2024, 1, 3), date(2024, 12, 31))
    bars = svc.normalize_bars(svc.StooqProvider().parse(STOOQ_CSV, request), request)

    assert list(bars.columns) == svc.BAR_COLUMNS
    assert [ts.date().isoformat() for ts in bars["timestamp"]] == ["2024-01-03", "2024-01-04"]
    assert bars["close"].tolist() == [184.25, 181.91]
    assert bars["volume"].dtype == "int64"


def test_stooq_url_maps_us_tickers() -> None:
    request = svc.FetchRequest("AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert svc.StooqProvider().url(request) == (
        "https://stooq.com/q/d/l/?s=aapl.us&d1=20240101&d2=20240131&i=d"
    )


def test_stooq_parse_rejects_no_data_body() -> None:
    request = svc.FetchRequest("ZZZZ", date(2024, 1, 1), date(2024, 1, 31))
    with pytest.raises(svc.MarketDataError):
        svc.StooqProvider().parse("No data", request)


def test_yahoo_parse_skips_null_rows() -> None:
    request = svc.FetchRequest("MSFT", date(2024, 1, 1), date(2024, 1, 31))
    # 2024-01-02 and 2024-01-03 at 14:30 UTC
    body = yahoo_body([1704205800, 1704292200], [370.0, None])
    bars = svc.normalize_bars(svc.YahooProvider().parse(body, request), request)

    assert len(bars) == 1
    assert bars.iloc[0]["timestamp"].date() == date(2024, 1, 2)
    assert bars.iloc[0]["close"] == 370.0


def test_yahoo_parse_surfaces_provider_error() -> None:
    request = svc.FetchRequest("MSFT", date(2024, 1, 1), date(2024, 1, 31))
    body = json.dumps({"chart": {"result": None, "error": {"description": "No data found"}}})
    with pytest.raises(svc.MarketDataError, match="No data found"):
        svc.YahooProvider().parse(body, request)


@pytest.mark.asyncio
async def test_fetch_daily_bars_falls_back_to_second_provider() -> None:
    request = svc.FetchRequest("AAPL", date(2024, 1, 1), date(2024, 1, 31))

    def handler(http_request: httpx.Request) -> httpx.Response:
        if "stooq.com" in str(http_request.url):
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text=yahoo_body([1704205800], [185.0]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        bars, provider = await svc.fetch_daily_bars(
            request, client=client, providers=[svc.StooqProvider(), svc.YahooProvider()]
        )

    assert provider == "yahoo"
    assert len(bars) == 1


@pytest.mark.asyncio
async def test_fetch_daily_bars_reports_every_failure() -> None:
    request = svc.FetchRequest("AAPL", date(2024, 1, 1), date(2024, 1, 31))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="nope")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(svc.MarketDataError) as excinfo:
            await svc.fetch_daily_bars(
                request, client=client, providers=[svc.StooqProvider(), svc.YahooProvider()]
            )

    assert "stooq" in str(excinfo.value)
    assert "yahoo" in str(excinfo.value)


def test_write_dataset_file_and_checksum(tmp_path: Path) -> None:
    request = svc.FetchRequest("AAPL", date(2024, 1, 1), date(2024, 12, 31))
    bars = svc.normalize_bars(svc.StooqProvider().parse(STOOQ_CSV, request), request)

    path = svc.write_dataset_file("AAPL", bars, tmp_path / "market")

    assert path == tmp_path / "market" / "AAPL_1d.parquet"
    reloaded = pd.read_parquet(path)
    assert list(reloaded.columns) == svc.BAR_COLUMNS
    assert len(reloaded) == 3
    assert len(svc.file_checksum(path)) == 64
    assert svc.stored_file_path(path, tmp_path) == "market/AAPL_1d.parquet"


class FakeDb:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.added = []
        self.commits = 0

    async def scalar(self, _statement):
        return self.existing

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()


@pytest.mark.asyncio
async def test_register_dataset_creates_row_from_bars() -> None:
    request = svc.FetchRequest("AAPL", date(2024, 1, 1), date(2024, 12, 31))
    bars = svc.normalize_bars(svc.StooqProvider().parse(STOOQ_CSV, request), request)
    db = FakeDb()

    dataset = await svc.register_dataset(
        db,
        symbol="AAPL",
        bars=bars,
        file_path="data/market/AAPL_1d.parquet",
        checksum="abc",
        source="stooq",
    )

    assert db.added == [dataset]
    assert db.commits == 1
    assert dataset.name == "AAPL Daily"
    assert dataset.symbols == ["AAPL"]
    assert dataset.start_date == date(2024, 1, 2)
    assert dataset.end_date == date(2024, 1, 4)
    assert dataset.row_count == 3
    assert dataset.source == "stooq"


@pytest.mark.asyncio
async def test_register_dataset_updates_existing_row() -> None:
    request = svc.FetchRequest("AAPL", date(2024, 1, 1), date(2024, 12, 31))
    bars = svc.normalize_bars(svc.StooqProvider().parse(STOOQ_CSV, request), request)
    existing = SimpleNamespace(
        id=uuid.uuid4(), file_path="data/market/AAPL_1d.parquet", checksum="old", row_count=1
    )
    db = FakeDb(existing=existing)

    dataset = await svc.register_dataset(
        db,
        symbol="AAPL",
        bars=bars,
        file_path="data/market/AAPL_1d.parquet",
        checksum="new",
        source="yahoo",
    )

    assert dataset is existing
    assert db.added == []
    assert dataset.checksum == "new"
    assert dataset.row_count == 3
    assert dataset.source == "yahoo"
