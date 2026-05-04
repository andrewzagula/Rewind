import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.schemas.run import CompareEquityPoint, ComparedRun, CompareResponse, MetricDelta
from app.services import chat_context_service

NOW = datetime(2026, 5, 3, tzinfo=UTC)


def _run(run_id: uuid.UUID, strategy_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=run_id,
        strategy_id=strategy_id,
        status="completed",
        params={"symbol": "AAPL", "initial_cash": 100000},
        metrics={"total_return": -0.12, "total_trades": 1},
        artifacts={"equity_curve": [100000, 98000, 88000]},
        error=None,
        started_at=NOW,
        completed_at=NOW,
        created_at=NOW,
        dataset_version="sample",
    )


def _strategy(strategy_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=strategy_id,
        name="Mean Reversion",
        description="Test strategy",
        version=3,
        code="class MeanReversion(Strategy):\n    pass",
        created_at=NOW,
        updated_at=NOW,
    )


def _trade(run_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        run_id=run_id,
        symbol="AAPL",
        side="sell",
        quantity=Decimal("10"),
        price=Decimal("190.50"),
        timestamp=NOW,
        pnl=Decimal("-250.25"),
    )


def test_normalize_context_selector_accepts_run_and_compare_contexts() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()

    assert chat_context_service.normalize_context_selector(
        {"type": "run", "run_id": str(first_id)}
    ) == {"type": "run", "run_id": str(first_id)}
    assert chat_context_service.normalize_context_selector(
        {"type": "compare", "run_ids": [str(first_id), str(second_id), str(first_id)]}
    ) == {"type": "compare", "run_ids": [str(first_id), str(second_id)]}


def test_normalize_context_selector_rejects_invalid_contexts() -> None:
    with pytest.raises(chat_context_service.ChatContextValidationError):
        chat_context_service.normalize_context_selector({"type": "compare", "run_ids": ["bad"]})

    with pytest.raises(chat_context_service.ChatContextValidationError):
        chat_context_service.normalize_context_selector({"type": "other"})


def test_message_linking_helpers_use_run_links_and_compare_metadata() -> None:
    run_id = uuid.uuid4()
    run_context = {"type": "run", "run_id": str(run_id)}
    compare_context = {"type": "compare", "run_ids": [str(run_id), str(uuid.uuid4())]}

    assert chat_context_service.linked_run_id(run_context) == run_id
    assert chat_context_service.message_metadata(run_context) == {}
    assert chat_context_service.linked_run_id(compare_context) is None
    assert chat_context_service.message_metadata(compare_context) == {"context": compare_context}


@pytest.mark.asyncio
async def test_build_prompt_context_includes_run_strategy_trades_and_equity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid.uuid4()
    strategy_id = uuid.uuid4()
    run = _run(run_id, strategy_id)
    strategy = _strategy(strategy_id)
    trade = _trade(run_id)

    async def get_run(_db: object, current_run_id: uuid.UUID) -> SimpleNamespace | None:
        return run if current_run_id == run_id else None

    async def get_strategy(
        _db: object, current_strategy_id: uuid.UUID
    ) -> SimpleNamespace | None:
        return strategy if current_strategy_id == strategy_id else None

    async def get_run_trades(
        _db: object,
        current_run_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "timestamp",
        sort_dir: str = "asc",
    ) -> tuple[list[SimpleNamespace], int]:
        assert current_run_id == run_id
        assert limit == chat_context_service.MAX_CONTEXT_TRADES
        assert sort_by == "timestamp"
        assert sort_dir == "asc"
        return [trade], 1

    monkeypatch.setattr(chat_context_service.run_service, "get_run", get_run)
    monkeypatch.setattr(chat_context_service.strategy_service, "get_strategy", get_strategy)
    monkeypatch.setattr(chat_context_service.run_service, "get_run_trades", get_run_trades)

    context = await chat_context_service.build_prompt_context(
        object(),
        {"type": "run", "run_id": str(run_id)},
    )

    assert context["context_type"] == "run"
    assert context["run"]["metrics"]["total_return"] == -0.12
    assert context["strategy"]["code"] == strategy.code
    assert context["trades"]["items"][0]["pnl"] == -250.25
    assert context["artifacts"]["equity"]["point_count"] == 3
    assert context["limitations"] == []


@pytest.mark.asyncio
async def test_build_prompt_context_includes_compare_metric_deltas_without_trades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_run_id = uuid.uuid4()
    second_run_id = uuid.uuid4()
    strategy_id = uuid.uuid4()
    strategy = _strategy(strategy_id)
    comparison = CompareResponse(
        runs=[
            ComparedRun(
                id=first_run_id,
                strategy_id=strategy_id,
                status="completed",
                params={"symbol": "AAPL"},
                metrics={"total_return": -0.12},
                error=None,
                created_at=NOW,
                completed_at=NOW,
                equity_points=[CompareEquityPoint(index=0, value=100000)],
            ),
            ComparedRun(
                id=second_run_id,
                strategy_id=strategy_id,
                status="completed",
                params={"symbol": "AAPL"},
                metrics={"total_return": 0.08},
                error=None,
                created_at=NOW,
                completed_at=NOW,
                equity_points=[CompareEquityPoint(index=0, value=100000)],
            ),
        ],
        metric_deltas=[
            MetricDelta(
                key="total_return",
                base=-0.12,
                values=[-0.12, 0.08],
                deltas=[0.0, 0.2],
            )
        ],
    )

    async def compare_runs(_db: object, run_ids: list[uuid.UUID]) -> CompareResponse:
        assert run_ids == [first_run_id, second_run_id]
        return comparison

    async def get_strategy(
        _db: object, current_strategy_id: uuid.UUID
    ) -> SimpleNamespace | None:
        return strategy if current_strategy_id == strategy_id else None

    monkeypatch.setattr(chat_context_service.compare_service, "compare_runs", compare_runs)
    monkeypatch.setattr(chat_context_service.strategy_service, "get_strategy", get_strategy)

    context = await chat_context_service.build_prompt_context(
        object(),
        {"type": "compare", "run_ids": [str(first_run_id), str(second_run_id)]},
    )

    assert context["context_type"] == "compare"
    assert context["metric_deltas"][0]["key"] == "total_return"
    assert context["metric_deltas"][0]["deltas"] == [0.0, 0.2]
    assert context["runs"][1]["metrics"]["total_return"] == 0.08
    assert context["strategies"][0]["code"] == strategy.code
    assert "trades" not in context
