import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.services import compare_service, run_service, strategy_service

MAX_CONTEXT_TRADES = 50


class ChatContextValidationError(Exception):
    pass


class ChatContextNotFoundError(Exception):
    pass


def normalize_context_selector(context: dict[str, Any]) -> dict[str, Any]:
    if not context:
        return {}

    context_type = context.get("type")
    if context_type == "run":
        run_id = _parse_uuid(context.get("run_id"), "context.run_id")
        return {"type": "run", "run_id": str(run_id)}

    if context_type == "compare":
        raw_run_ids = context.get("run_ids")
        if not isinstance(raw_run_ids, list):
            raise ChatContextValidationError("context.run_ids must be a list of run IDs")

        parsed_run_ids = [
            _parse_uuid(raw_run_id, f"context.run_ids[{index}]")
            for index, raw_run_id in enumerate(raw_run_ids)
        ]
        try:
            unique_run_ids = compare_service.unique_run_ids(parsed_run_ids)
        except ValueError as exc:
            raise ChatContextValidationError(str(exc)) from exc

        return {"type": "compare", "run_ids": [str(run_id) for run_id in unique_run_ids]}

    raise ChatContextValidationError("context.type must be either run or compare")


async def build_prompt_context(db: AsyncSession, selector: dict[str, Any]) -> dict[str, Any]:
    if not selector:
        return {}

    normalized = normalize_context_selector(selector)
    if normalized.get("type") == "run":
        return await _build_run_context(db, uuid.UUID(str(normalized["run_id"])))

    if normalized.get("type") == "compare":
        run_ids = [uuid.UUID(str(run_id)) for run_id in normalized["run_ids"]]
        return await _build_compare_context(db, run_ids)

    return {}


def linked_run_id(selector: dict[str, Any]) -> uuid.UUID | None:
    if selector.get("type") != "run":
        return None
    return uuid.UUID(str(selector["run_id"]))


def message_metadata(selector: dict[str, Any]) -> dict[str, Any]:
    if selector.get("type") == "compare":
        return {"context": selector}
    return {}


async def _build_run_context(db: AsyncSession, run_id: uuid.UUID) -> dict[str, Any]:
    run = await run_service.get_run(db, run_id)
    if run is None:
        raise ChatContextNotFoundError("Run not found")

    strategy = await strategy_service.get_strategy(db, run.strategy_id)
    trades, total = await run_service.get_run_trades(
        db,
        run_id,
        limit=MAX_CONTEXT_TRADES,
        offset=0,
        sort_by="timestamp",
        sort_dir="asc",
    )

    equity = _equity_summary(run.artifacts or {})
    limitations = _run_limitations(run, strategy, total, len(trades), equity)

    return {
        "context_type": "run",
        "run": _run_payload(run),
        "strategy": _strategy_payload(strategy),
        "trades": {
            "total": total,
            "included": len(trades),
            "items": [_trade_payload(trade) for trade in trades],
        },
        "artifacts": {"equity": equity},
        "limitations": limitations,
    }


async def _build_compare_context(db: AsyncSession, run_ids: list[uuid.UUID]) -> dict[str, Any]:
    try:
        comparison = await compare_service.compare_runs(db, run_ids)
    except compare_service.MissingRunsError as exc:
        missing = ", ".join(str(run_id) for run_id in exc.missing_ids)
        raise ChatContextNotFoundError(f"Runs not found: {missing}") from exc
    except ValueError as exc:
        raise ChatContextValidationError(str(exc)) from exc

    strategy_ids = []
    seen_strategy_ids: set[uuid.UUID] = set()
    for run in comparison.runs:
        if run.strategy_id in seen_strategy_ids:
            continue
        seen_strategy_ids.add(run.strategy_id)
        strategy_ids.append(run.strategy_id)

    strategies = [
        _strategy_payload(strategy)
        for strategy_id in strategy_ids
        if (strategy := await strategy_service.get_strategy(db, strategy_id)) is not None
    ]
    limitations = _compare_limitations(comparison, len(strategies), len(strategy_ids))

    return {
        "context_type": "compare",
        "run_ids": [str(run_id) for run_id in run_ids],
        "runs": [
            {
                "id": str(run.id),
                "strategy_id": str(run.strategy_id),
                "status": run.status,
                "params": run.params,
                "metrics": run.metrics,
                "error": run.error,
                "created_at": _isoformat(run.created_at),
                "completed_at": _isoformat(run.completed_at),
                "equity": _equity_summary_from_points(
                    [point.model_dump() for point in run.equity_points]
                ),
            }
            for run in comparison.runs
        ],
        "metric_deltas": [delta.model_dump() for delta in comparison.metric_deltas],
        "strategies": strategies,
        "limitations": limitations,
    }


def _parse_uuid(value: Any, field: str) -> uuid.UUID:
    if not isinstance(value, str):
        raise ChatContextValidationError(f"{field} must be a UUID string")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ChatContextValidationError(f"{field} must be a valid UUID") from exc


def _run_payload(run: Run) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "strategy_id": str(run.strategy_id),
        "status": run.status,
        "params": run.params or {},
        "metrics": run.metrics or {},
        "error": run.error,
        "started_at": _isoformat(run.started_at),
        "completed_at": _isoformat(run.completed_at),
        "created_at": _isoformat(run.created_at),
        "dataset_version": run.dataset_version,
    }


def _strategy_payload(strategy: Strategy | None) -> dict[str, Any] | None:
    if strategy is None:
        return None

    return {
        "id": str(strategy.id),
        "name": strategy.name,
        "description": strategy.description,
        "version": strategy.version,
        "code": strategy.code,
        "created_at": _isoformat(strategy.created_at),
        "updated_at": _isoformat(strategy.updated_at),
    }


def _trade_payload(trade: Trade) -> dict[str, Any]:
    return {
        "id": str(trade.id),
        "run_id": str(trade.run_id),
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": _number(trade.quantity),
        "price": _number(trade.price),
        "timestamp": _isoformat(trade.timestamp),
        "pnl": _number(trade.pnl),
    }


def _equity_summary(artifacts: dict[str, Any]) -> dict[str, Any]:
    points = [point.model_dump() for point in compare_service.normalize_equity_points(artifacts)]
    return _equity_summary_from_points(points)


def _equity_summary_from_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_number(point.get("value")) for point in points]
    values = [value for value in values if value is not None]

    if not values:
        return {"point_count": 0}

    return {
        "point_count": len(values),
        "first_value": values[0],
        "last_value": values[-1],
        "min_value": min(values),
        "max_value": max(values),
        "max_drawdown": _max_drawdown(values),
        "start_timestamp": str(points[0].get("timestamp") or ""),
        "end_timestamp": str(points[-1].get("timestamp") or ""),
        "sample_points": _sample_points(points),
    }


def _sample_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(points) <= 10:
        return points
    return [*points[:5], *points[-5:]]


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    max_drawdown = 0.0

    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value - peak) / peak)

    return max_drawdown


def _run_limitations(
    run: Run,
    strategy: Strategy | None,
    trade_total: int,
    included_trade_count: int,
    equity: dict[str, Any],
) -> list[str]:
    limitations = []
    if not run.metrics:
        limitations.append("No run metrics are available.")
    if trade_total == 0:
        limitations.append("No trades are available for this run.")
    elif trade_total > included_trade_count:
        limitations.append(
            f"Only the first {included_trade_count} of {trade_total} chronological trades are included."
        )
    if equity.get("point_count", 0) == 0:
        limitations.append("No equity curve artifact is available.")
    if strategy is None:
        limitations.append("The linked strategy record was not found.")
    if run.status != "completed":
        limitations.append(f"The run is {run.status}; final backtest results may be unavailable.")
    return limitations


def _compare_limitations(comparison: Any, strategy_count: int, expected_strategy_count: int) -> list[str]:
    limitations = []
    for run in comparison.runs:
        if not run.metrics:
            limitations.append(f"Run {run.id} has no metrics.")
        if len(run.equity_points) == 0:
            limitations.append(f"Run {run.id} has no equity curve artifact.")
        if run.status != "completed":
            limitations.append(f"Run {run.id} is {run.status}; final results may be unavailable.")
    if strategy_count < expected_strategy_count:
        limitations.append("One or more linked strategy records were not found.")
    if not comparison.metric_deltas:
        limitations.append("No comparable numeric metric deltas are available.")
    return limitations


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return None
