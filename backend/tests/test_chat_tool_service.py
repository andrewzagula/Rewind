import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services import (
    chat_tool_service,
    dataset_service,
    job_service,
    run_service,
    strategy_service,
)

NOW = datetime(2026, 9, 2, tzinfo=UTC)
VALID_CODE = """from engine import Signal, Strategy


class HoldStrategy(Strategy):
    def init(self, params):
        self.done = False

    def next(self, row, portfolio):
        if not self.done:
            self.done = True
            return Signal(symbol=row["symbol"], side="buy", quantity=10)
        return None
"""


class FakeDb:
    def __init__(self) -> None:
        self.refreshes = 0

    async def refresh(self, run) -> None:
        self.refreshes += 1
        run.status = "completed"
        run.metrics = {"total_return": 0.05, "sharpe_ratio": 0.8}
        run.completed_at = NOW


def strategy(strategy_id=None):
    return SimpleNamespace(
        id=strategy_id or uuid.uuid4(),
        name="Hold",
        description="",
        code=VALID_CODE,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def dataset(symbol="AAPL", source="stooq"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=f"{symbol} Daily",
        symbols=[symbol],
        timeframe="1d",
        start_date=NOW.date(),
        end_date=NOW.date(),
        row_count=10,
        file_path=f"data/market/{symbol}_1d.parquet",
        checksum="x",
        source=source,
        created_at=NOW,
    )


@pytest.mark.asyncio
async def test_unknown_tool_returns_error() -> None:
    result = await chat_tool_service.execute_tool(FakeDb(), "launch_rockets", {})
    assert result == {"error": "Unknown tool: launch_rockets"}


@pytest.mark.asyncio
async def test_list_strategies_clamps_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    async def list_strategies(_db, limit=20, offset=0):
        seen["limit"] = limit
        return [strategy()], 1

    monkeypatch.setattr(strategy_service, "list_strategies", list_strategies)

    result = await chat_tool_service.execute_tool(FakeDb(), "list_strategies", {"limit": 500})

    assert seen["limit"] == 50
    assert result["total"] == 1
    assert result["items"][0]["name"] == "Hold"
    assert "code" not in result["items"][0]


@pytest.mark.asyncio
async def test_get_strategy_requires_valid_uuid() -> None:
    result = await chat_tool_service.execute_tool(FakeDb(), "get_strategy", {"strategy_id": "nope"})
    assert result == {"error": "strategy_id must be a valid UUID"}


@pytest.mark.asyncio
async def test_create_strategy_reports_validation_errors() -> None:
    result = await chat_tool_service.execute_tool(
        FakeDb(), "create_strategy", {"name": "Bad", "code": "import os\nos.system('rm -rf /')"}
    )
    assert "error" in result
    assert "Strategy" in result["error"] or "strategy" in result["error"]


@pytest.mark.asyncio
async def test_run_backtest_picks_real_dataset_and_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    strat = strategy()
    synthetic = dataset("AAPL", source="synthetic")
    real = dataset("AAPL", source="stooq")
    enqueued: list[uuid.UUID] = []
    created: dict = {}

    async def get_strategy(_db, strategy_id):
        return strat if strategy_id == strat.id else None

    async def list_datasets(_db, limit=100, offset=0):
        return [synthetic, real], 2

    async def create_run(_db, data, dataset=None):
        created["dataset"] = dataset
        created["params"] = data.params
        return SimpleNamespace(
            id=uuid.uuid4(),
            strategy_id=data.strategy_id,
            dataset_id=dataset.id if dataset else None,
            dataset_version=dataset.checksum if dataset else "",
            params=data.params,
            metrics={},
            artifacts={},
            status="pending",
            error=None,
            started_at=None,
            completed_at=None,
            created_at=NOW,
        )

    async def enqueue_backtest(run_id):
        enqueued.append(run_id)

    monkeypatch.setattr(strategy_service, "get_strategy", get_strategy)
    monkeypatch.setattr(dataset_service, "list_datasets", list_datasets)
    monkeypatch.setattr(run_service, "create_run", create_run)
    monkeypatch.setattr(job_service, "enqueue_backtest", enqueue_backtest)
    monkeypatch.setattr(chat_tool_service, "RUN_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(chat_tool_service.settings, "chat_tool_run_timeout_seconds", 2.0)

    db = FakeDb()
    result = await chat_tool_service.execute_tool(
        db, "run_backtest", {"strategy_id": str(strat.id), "params": {"symbol": "aapl"}}
    )

    assert created["dataset"] is real
    assert enqueued and db.refreshes == 1
    assert result["run"]["status"] == "completed"
    assert result["run"]["metrics"]["total_return"] == 0.05
    assert result["run"]["dataset"]["source"] == "stooq"
    assert "note" not in result["run"]


@pytest.mark.asyncio
async def test_run_backtest_notes_when_still_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    strat = strategy()

    async def get_strategy(_db, strategy_id):
        return strat

    async def create_run(_db, data, dataset=None):
        return SimpleNamespace(
            id=uuid.uuid4(),
            strategy_id=data.strategy_id,
            dataset_id=None,
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

    async def enqueue_backtest(run_id):
        return None

    class StuckDb:
        async def refresh(self, run):
            return None

    monkeypatch.setattr(strategy_service, "get_strategy", get_strategy)
    monkeypatch.setattr(run_service, "create_run", create_run)
    monkeypatch.setattr(job_service, "enqueue_backtest", enqueue_backtest)
    monkeypatch.setattr(chat_tool_service, "RUN_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(chat_tool_service.settings, "chat_tool_run_timeout_seconds", 0.05)

    result = await chat_tool_service.execute_tool(
        StuckDb(), "run_backtest", {"strategy_id": str(strat.id)}
    )

    assert result["run"]["status"] == "pending"
    assert "still in progress" in result["run"]["note"]


@pytest.mark.asyncio
async def test_run_backtest_rejects_missing_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    strat = strategy()

    async def get_strategy(_db, strategy_id):
        return strat

    async def get_dataset(_db, dataset_id):
        return None

    monkeypatch.setattr(strategy_service, "get_strategy", get_strategy)
    monkeypatch.setattr(dataset_service, "get_dataset", get_dataset)

    result = await chat_tool_service.execute_tool(
        FakeDb(), "run_backtest", {"strategy_id": str(strat.id), "dataset_id": str(uuid.uuid4())}
    )
    assert result == {"error": "Dataset not found"}


def test_summarize_tool_result_for_runs_and_errors() -> None:
    run_id = str(uuid.uuid4())
    described = chat_tool_service.summarize_tool_result(
        "run_backtest",
        {},
        {
            "run": {
                "id": run_id,
                "status": "completed",
                "metrics": {"total_return": 0.1234, "sharpe_ratio": 1.234},
            }
        },
    )
    assert described["summary"] == f"Run {run_id[:8]} completed, return 12.34%, Sharpe 1.23."
    assert described["href"] == f"/runs/{run_id}"

    failed = chat_tool_service.summarize_tool_result("get_run", {}, {"error": "Run not found"})
    assert failed == {"summary": "Run not found", "href": ""}

    fetched = chat_tool_service.summarize_tool_result(
        "fetch_market_data",
        {"symbol": "NVDA"},
        {"dataset": {"row_count": 1250, "symbols": ["NVDA"], "source": "stooq"}},
    )
    assert fetched["summary"] == "Fetched 1250 daily bars for NVDA from stooq."
    assert fetched["href"] == "/datasets"


def test_tool_definitions_are_well_formed() -> None:
    names = [tool["function"]["name"] for tool in chat_tool_service.TOOL_DEFINITIONS]
    assert len(names) == len(set(names))
    assert set(names) == set(chat_tool_service._HANDLERS)
    assert "delete_strategy" not in names
