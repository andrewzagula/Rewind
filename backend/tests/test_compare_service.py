import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services import compare_service


class _Scalars:
    def __init__(self, runs: list[SimpleNamespace]) -> None:
        self._runs = runs

    def all(self) -> list[SimpleNamespace]:
        return self._runs


class _Result:
    def __init__(self, runs: list[SimpleNamespace]) -> None:
        self._runs = runs

    def scalars(self) -> _Scalars:
        return _Scalars(self._runs)


class _FakeDb:
    def __init__(self, runs: list[SimpleNamespace]) -> None:
        self._runs = runs

    async def execute(self, _statement: object) -> _Result:
        return _Result(self._runs)


def _run(
    run_id: uuid.UUID,
    *,
    metrics: dict,
    artifacts: dict | None = None,
    status: str = "completed",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=run_id,
        strategy_id=uuid.uuid4(),
        status=status,
        params={"symbol": "AAPL"},
        metrics=metrics,
        artifacts=artifacts or {},
        error=None,
        created_at=datetime(2026, 5, 3, tzinfo=UTC),
        completed_at=datetime(2026, 5, 3, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_compare_runs_preserves_request_order_and_builds_metric_deltas() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    first = _run(first_id, metrics={"total_return": 0.1, "sharpe_ratio": 1.2})
    second = _run(second_id, metrics={"total_return": 0.25, "sharpe_ratio": 0.7})

    response = await compare_service.compare_runs(_FakeDb([second, first]), [first_id, second_id])

    assert [run.id for run in response.runs] == [first_id, second_id]
    total_return = next(delta for delta in response.metric_deltas if delta.key == "total_return")
    assert total_return.base == 0.1
    assert total_return.values == [0.1, 0.25]
    assert total_return.deltas == [0.0, 0.15]


@pytest.mark.asyncio
async def test_compare_runs_raises_for_missing_runs() -> None:
    existing_id = uuid.uuid4()
    missing_id = uuid.uuid4()

    with pytest.raises(compare_service.MissingRunsError) as exc:
        await compare_service.compare_runs(
            _FakeDb([_run(existing_id, metrics={})]),
            [existing_id, missing_id],
        )

    assert exc.value.missing_ids == [missing_id]


def test_normalize_equity_points_falls_back_to_equity_curve() -> None:
    points = compare_service.normalize_equity_points(
        {"equity_curve": [100000, 100500, "bad", 101000]}
    )

    assert [point.model_dump() for point in points] == [
        {"index": 0, "timestamp": "", "value": 100000.0},
        {"index": 1, "timestamp": "", "value": 100500.0},
        {"index": 3, "timestamp": "", "value": 101000.0},
    ]


def test_unique_run_ids_requires_two_unique_ids() -> None:
    run_id = uuid.uuid4()

    with pytest.raises(ValueError, match="At least 2 unique run IDs"):
        compare_service.unique_run_ids([run_id, run_id])
