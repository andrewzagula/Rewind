import math
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run
from app.schemas.run import ComparedRun, CompareEquityPoint, CompareResponse, MetricDelta

METRIC_KEYS = [
    "total_return",
    "annualized_return",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "calmar_ratio",
    "volatility_annual",
    "total_trades",
    "win_rate",
    "profit_factor",
    "avg_trade_pnl",
    "avg_win",
    "avg_loss",
]


class MissingRunsError(Exception):
    def __init__(self, missing_ids: Sequence[uuid.UUID]) -> None:
        self.missing_ids = list(missing_ids)
        super().__init__("Missing runs: " + ", ".join(str(run_id) for run_id in missing_ids))


def unique_run_ids(run_ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
    ordered_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()

    for run_id in run_ids:
        if run_id in seen:
            continue
        seen.add(run_id)
        ordered_ids.append(run_id)

    if len(ordered_ids) < 2:
        raise ValueError("At least 2 unique run IDs are required")

    return ordered_ids


def normalize_equity_points(artifacts: dict[str, Any] | None) -> list[CompareEquityPoint]:
    if not artifacts:
        return []

    raw_points = artifacts.get("equity_points")
    if isinstance(raw_points, list):
        points: list[CompareEquityPoint] = []
        for fallback_index, raw_point in enumerate(raw_points):
            if not isinstance(raw_point, dict):
                continue

            value = _finite_float(raw_point.get("value"))
            if value is None:
                continue

            index = _safe_int(raw_point.get("index"), fallback_index)
            timestamp = raw_point.get("timestamp")
            points.append(
                CompareEquityPoint(
                    index=index,
                    timestamp="" if timestamp is None else str(timestamp),
                    value=value,
                )
            )
        return points

    raw_curve = artifacts.get("equity_curve")
    if not isinstance(raw_curve, list):
        return []

    points = []
    for index, raw_value in enumerate(raw_curve):
        value = _finite_float(raw_value)
        if value is None:
            continue
        points.append(CompareEquityPoint(index=index, timestamp="", value=value))
    return points


def build_compared_run(run: Run) -> ComparedRun:
    return ComparedRun(
        id=run.id,
        strategy_id=run.strategy_id,
        status=run.status,
        params=run.params or {},
        metrics=run.metrics or {},
        error=run.error,
        created_at=run.created_at,
        completed_at=run.completed_at,
        equity_points=normalize_equity_points(run.artifacts or {}),
    )


def build_metric_deltas(runs: Sequence[ComparedRun]) -> list[MetricDelta]:
    if not runs:
        return []

    deltas: list[MetricDelta] = []
    base_metrics = runs[0].metrics

    for key in METRIC_KEYS:
        values = [_finite_float(run.metrics.get(key)) for run in runs]
        if all(value is None for value in values):
            continue

        base = _finite_float(base_metrics.get(key))
        metric_deltas = [
            value - base if value is not None and base is not None else None for value in values
        ]
        deltas.append(MetricDelta(key=key, base=base, values=values, deltas=metric_deltas))

    return deltas


async def compare_runs(db: AsyncSession, run_ids: Sequence[uuid.UUID]) -> CompareResponse:
    ordered_ids = unique_run_ids(run_ids)
    result = await db.execute(select(Run).where(Run.id.in_(ordered_ids)))
    runs_by_id = {run.id: run for run in result.scalars().all()}
    missing_ids = [run_id for run_id in ordered_ids if run_id not in runs_by_id]

    if missing_ids:
        raise MissingRunsError(missing_ids)

    compared_runs = [build_compared_run(runs_by_id[run_id]) for run_id in ordered_ids]
    return CompareResponse(
        runs=compared_runs,
        metric_deltas=build_metric_deltas(compared_runs),
    )


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _safe_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    return fallback
