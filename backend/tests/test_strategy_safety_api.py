import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.api.v1 import runs as runs_api
from app.services import run_service, strategy_service

NOW = datetime(2026, 5, 4, tzinfo=UTC)
VALID_STRATEGY_CODE = """from engine import Signal, Strategy


class MovingAverageStrategy(Strategy):
    def init(self, params: dict) -> None:
        self.window = int(params.get("window", 20))
        self.closes = []

    def next(self, row: dict, portfolio) -> Signal | None:
        self.closes.append(row["close"])
        if len(self.closes) < self.window:
            return None
        average = sum(self.closes[-self.window:]) / self.window
        if row["close"] > average and row["symbol"] not in portfolio.position_symbols:
            return Signal(symbol=row["symbol"], side="buy", quantity=10)
        return None
"""


@pytest.mark.asyncio
async def test_create_strategy_rejects_invalid_code_before_persistence(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail_create_strategy(_db: object, _data: object) -> None:
        raise AssertionError("create_strategy should not be called")

    monkeypatch.setattr(strategy_service, "create_strategy", fail_create_strategy)

    response = await client.post(
        "/api/v1/strategies",
        json={
            "name": "Broken",
            "description": "",
            "code": "class BrokenStrategy(Strategy):\n    pass",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Strategy code is invalid: BrokenStrategy must define init().; "
        "BrokenStrategy must define next()."
    )


@pytest.mark.asyncio
async def test_update_strategy_rejects_invalid_code_before_update(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail_update_strategy(
        _db: object, _strategy_id: uuid.UUID, _data: object
    ) -> None:
        raise AssertionError("update_strategy should not be called")

    monkeypatch.setattr(strategy_service, "update_strategy", fail_update_strategy)

    response = await client.patch(
        f"/api/v1/strategies/{uuid.uuid4()}",
        json={"code": "class BrokenStrategy(Strategy):\n    pass"},
    )

    assert response.status_code == 400
    assert "BrokenStrategy must define init()." in response.json()["detail"]
    assert "BrokenStrategy must define next()." in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_run_rejects_invalid_stored_strategy_before_queueing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    strategy_id = uuid.uuid4()

    async def get_strategy(_db: object, current_strategy_id: uuid.UUID) -> SimpleNamespace:
        assert current_strategy_id == strategy_id
        return SimpleNamespace(id=strategy_id, code="class BrokenStrategy(Strategy):\n    pass")

    async def fail_create_run(_db: object, _data: object) -> None:
        raise AssertionError("create_run should not be called")

    async def fail_get_pool() -> None:
        raise AssertionError("queue should not be opened")

    monkeypatch.setattr(strategy_service, "get_strategy", get_strategy)
    monkeypatch.setattr(run_service, "create_run", fail_create_run)
    monkeypatch.setattr(runs_api, "_get_arq_pool", fail_get_pool)

    response = await client.post(
        "/api/v1/runs",
        json={"strategy_id": str(strategy_id), "params": {"symbol": "AAPL"}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Strategy code is invalid: BrokenStrategy must define init().; "
        "BrokenStrategy must define next()."
    )


@pytest.mark.asyncio
async def test_create_run_enqueues_valid_strategy(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    strategy_id = uuid.uuid4()
    run_id = uuid.uuid4()

    class FakePool:
        def __init__(self) -> None:
            self.jobs: list[tuple[str, str]] = []
            self.closed = False

        async def enqueue_job(self, name: str, run_id_arg: str) -> None:
            self.jobs.append((name, run_id_arg))

        async def aclose(self) -> None:
            self.closed = True

    pool = FakePool()

    async def get_strategy(_db: object, current_strategy_id: uuid.UUID) -> SimpleNamespace:
        assert current_strategy_id == strategy_id
        return SimpleNamespace(id=strategy_id, code=VALID_STRATEGY_CODE)

    async def create_run(_db: object, data: object, dataset: object | None = None) -> SimpleNamespace:
        assert data.strategy_id == strategy_id
        assert dataset is None
        return SimpleNamespace(
            id=run_id,
            strategy_id=strategy_id,
            dataset_id=data.dataset_id,
            dataset_version="",
            params=data.params,
            metrics={},
            artifacts={},
            status="pending",
            error=None,
            started_at=None,
            completed_at=None,
            created_at=NOW,
        )

    async def get_pool() -> FakePool:
        return pool

    monkeypatch.setattr(strategy_service, "get_strategy", get_strategy)
    monkeypatch.setattr(run_service, "create_run", create_run)
    monkeypatch.setattr(runs_api, "_get_arq_pool", get_pool)

    response = await client.post(
        "/api/v1/runs",
        json={"strategy_id": str(strategy_id), "params": {"symbol": "AAPL"}},
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(run_id)
    assert response.json()["dataset_id"] is None
    assert response.json()["dataset_version"] == ""
    assert pool.jobs == [("run_backtest", str(run_id))]
    assert pool.closed is True


@pytest.mark.asyncio
async def test_create_run_rejects_missing_dataset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    strategy_id = uuid.uuid4()
    dataset_id = uuid.uuid4()

    async def get_strategy(_db: object, current_strategy_id: uuid.UUID) -> SimpleNamespace:
        assert current_strategy_id == strategy_id
        return SimpleNamespace(id=strategy_id, code=VALID_STRATEGY_CODE)

    async def get_dataset(_db: object, current_dataset_id: uuid.UUID) -> None:
        assert current_dataset_id == dataset_id
        return None

    async def fail_create_run(_db: object, _data: object, **_kwargs: object) -> None:
        raise AssertionError("create_run should not be called")

    async def fail_get_pool() -> None:
        raise AssertionError("queue should not be opened")

    monkeypatch.setattr(strategy_service, "get_strategy", get_strategy)
    monkeypatch.setattr(runs_api.dataset_service, "get_dataset", get_dataset)
    monkeypatch.setattr(run_service, "create_run", fail_create_run)
    monkeypatch.setattr(runs_api, "_get_arq_pool", fail_get_pool)

    response = await client.post(
        "/api/v1/runs",
        json={
            "strategy_id": str(strategy_id),
            "dataset_id": str(dataset_id),
            "params": {},
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found"
