import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.services import dataset_service

NOW = datetime(2026, 5, 5, tzinfo=UTC)


def _dataset(dataset_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=dataset_id or uuid.uuid4(),
        name="MSFT Sample Daily",
        symbols=["MSFT"],
        timeframe="1d",
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31),
        row_count=1305,
        file_path="data/sample/MSFT_1d.parquet",
        checksum="e614bd6b3a0dc4ab53c6f546fe736e4a331685fb04e2b79be437a8f7fc1cff36",
        created_at=NOW,
    )


@pytest.mark.asyncio
async def test_list_datasets_returns_items_total(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = _dataset()

    async def list_datasets(_db: object, limit: int = 100, offset: int = 0):
        assert limit == 25
        assert offset == 5
        return [dataset], 1

    monkeypatch.setattr(dataset_service, "list_datasets", list_datasets)

    response = await client.get("/api/v1/datasets?limit=25&offset=5")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(dataset.id)
    assert body["items"][0]["file_path"] == "data/sample/MSFT_1d.parquet"
    assert body["items"][0]["checksum"] == dataset.checksum


@pytest.mark.asyncio
async def test_get_dataset_returns_dataset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset_id = uuid.uuid4()
    dataset = _dataset(dataset_id)

    async def get_dataset(_db: object, current_dataset_id: uuid.UUID):
        assert current_dataset_id == dataset_id
        return dataset

    monkeypatch.setattr(dataset_service, "get_dataset", get_dataset)

    response = await client.get(f"/api/v1/datasets/{dataset_id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(dataset_id)


@pytest.mark.asyncio
async def test_get_dataset_returns_404_for_missing_dataset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def get_dataset(_db: object, _dataset_id: uuid.UUID):
        return None

    monkeypatch.setattr(dataset_service, "get_dataset", get_dataset)

    response = await client.get(f"/api/v1/datasets/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found"


@pytest.mark.asyncio
async def test_fetch_dataset_registers_real_data(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import market_data_service

    dataset = _dataset()
    dataset.name = "NVDA Daily"
    dataset.symbols = ["NVDA"]
    dataset.source = "stooq"
    captured: dict = {}

    async def fetch_and_register(_db, symbol, start_date=None, end_date=None, client=None):
        captured.update(symbol=symbol, start_date=start_date, end_date=end_date)
        return dataset

    monkeypatch.setattr(market_data_service, "fetch_and_register", fetch_and_register)

    response = await client.post(
        "/api/v1/datasets/fetch", json={"symbol": "nvda", "start_date": "2020-01-01"}
    )

    assert response.status_code == 201
    assert captured == {"symbol": "nvda", "start_date": date(2020, 1, 1), "end_date": None}
    body = response.json()
    assert body["symbols"] == ["NVDA"]
    assert body["source"] == "stooq"


@pytest.mark.asyncio
async def test_fetch_dataset_maps_validation_and_provider_errors(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import market_data_service

    async def bad_symbol(_db, symbol, start_date=None, end_date=None, client=None):
        raise market_data_service.MarketDataValidationError("Symbol must be valid")

    monkeypatch.setattr(market_data_service, "fetch_and_register", bad_symbol)
    response = await client.post("/api/v1/datasets/fetch", json={"symbol": "???"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Symbol must be valid"

    async def provider_down(_db, symbol, start_date=None, end_date=None, client=None):
        raise market_data_service.MarketDataError("Unable to fetch daily bars for ZZZZ.")

    monkeypatch.setattr(market_data_service, "fetch_and_register", provider_down)
    response = await client.post("/api/v1/datasets/fetch", json={"symbol": "ZZZZ"})
    assert response.status_code == 502
    assert "Unable to fetch" in response.json()["detail"]
