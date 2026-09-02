"""Tools the chat assistant can call directly.

Read tools look up strategies, runs, datasets, and comparisons. Write tools create or edit
strategies, queue backtests and wait for them, and fetch real market data. Deleting is
deliberately not a tool: the assistant proposes a ``delete_strategy`` action that the user
confirms in the UI instead.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.run import RunCreate
from app.schemas.strategy import StrategyCreate, StrategyUpdate
from app.services import (
    chat_context_service,
    dataset_service,
    job_service,
    market_data_service,
    run_service,
    strategy_service,
)
from app.services.strategy_validation_service import StrategyCodeValidationError

MAX_TOOL_ROUNDS = 8
RUN_POLL_INTERVAL_SECONDS = 0.5
TERMINAL_RUN_STATUSES = {"completed", "failed"}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_strategies",
            "description": "List saved strategies (newest first) with ids, names, and versions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_strategy",
            "description": "Get one strategy including its full Python code.",
            "parameters": {
                "type": "object",
                "properties": {"strategy_id": {"type": "string", "description": "Strategy UUID"}},
                "required": ["strategy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_runs",
            "description": (
                "List backtest runs (newest first) with status, params, and headline metrics. "
                "Optionally filter to one strategy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string", "description": "Optional strategy UUID"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_run",
            "description": (
                "Get a run's full results: metrics, params, dataset, strategy code, equity "
                "summary, and the first 50 trades."
            ),
            "parameters": {
                "type": "object",
                "properties": {"run_id": {"type": "string", "description": "Run UUID"}},
                "required": ["run_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_runs",
            "description": (
                "Compare two or more completed runs: metric deltas against the first run."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "run_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "description": "Run UUIDs; the first is the baseline.",
                    }
                },
                "required": ["run_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_datasets",
            "description": (
                "List registered price datasets with symbol, date range, row count, and source. "
                "Source 'synthetic' means randomly generated sample data, not real prices."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_market_data",
            "description": (
                "Download real daily OHLCV history for a ticker from a free provider and register "
                "it as a dataset. Use this when no real dataset exists for a symbol the user wants."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker such as AAPL or SPY"},
                    "start_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD, default 5 years ago",
                    },
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, default today"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_strategy",
            "description": (
                "Save a new strategy. Code must define exactly one Strategy subclass with init() "
                "and next(). Validation errors are returned so you can fix the code and retry."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "code": {"type": "string", "description": "Complete Python source"},
                },
                "required": ["name", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_strategy_code",
            "description": "Replace an existing strategy's code (bumps its version).",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "code": {"type": "string", "description": "Complete Python source"},
                },
                "required": ["strategy_id", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_backtest",
            "description": (
                "Queue a backtest for a strategy on a dataset and wait for it to finish. Returns "
                "the run id, status, metrics, and error. If the dataset_id is omitted, a dataset "
                "matching params.symbol is used when one exists. If the run is still pending when "
                "the wait ends, call get_run later."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "dataset_id": {"type": "string", "description": "Dataset UUID (recommended)"},
                    "params": {
                        "type": "object",
                        "description": (
                            "Strategy params such as symbol, timeframe, initial_cash, window. "
                            "Optional params.execution controls realism: omit for the realistic "
                            "default (next-open fills, 0.05% slippage, regulatory sell fees, "
                            "cash and position checks), pass \"ideal\" for frictionless "
                            "close fills, or an object like {\"slippage_pct\": 0.001, "
                            "\"commission_per_share\": 0.005, \"allow_short\": true}."
                        ),
                    },
                },
                "required": ["strategy_id"],
            },
        },
    },
]


class ToolExecutionError(Exception):
    pass


async def execute_tool(db: AsyncSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one tool. Errors are returned as ``{"error": ...}`` so the model can recover."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await handler(db, arguments or {})
    except (
        ToolExecutionError,
        StrategyCodeValidationError,
        run_service.DatasetRunValidationError,
        market_data_service.MarketDataError,
        chat_context_service.ChatContextValidationError,
        chat_context_service.ChatContextNotFoundError,
        ValueError,
    ) as exc:
        return {"error": str(exc)}


def summarize_tool_result(
    name: str, arguments: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """A compact, UI-friendly description of a tool call and where to look afterwards."""
    if "error" in result:
        return {"summary": str(result["error"]), "href": ""}

    if name == "list_strategies":
        return {"summary": f"Found {result.get('total', 0)} strategies.", "href": "/strategies"}
    if name == "get_strategy":
        strategy = result.get("strategy") or {}
        return {
            "summary": (
                f"Loaded strategy {strategy.get('name', '')} v{strategy.get('version', '')}."
            ),
            "href": f"/strategies/{strategy.get('id', '')}" if strategy.get("id") else "",
        }
    if name == "list_runs":
        return {"summary": f"Found {result.get('total', 0)} runs.", "href": "/runs"}
    if name == "get_run":
        run = result.get("run") or {}
        return {
            "summary": f"Loaded run {str(run.get('id', ''))[:8]} ({run.get('status', '')}).",
            "href": f"/runs/{run.get('id', '')}" if run.get("id") else "",
        }
    if name == "compare_runs":
        run_ids = result.get("run_ids") or []
        return {
            "summary": f"Compared {len(run_ids)} runs.",
            "href": f"/compare?runs={','.join(run_ids)}" if run_ids else "/compare",
        }
    if name == "list_datasets":
        return {"summary": f"Found {result.get('total', 0)} datasets.", "href": "/datasets"}
    if name == "fetch_market_data":
        dataset = result.get("dataset") or {}
        return {
            "summary": (
                f"Fetched {dataset.get('row_count', 0)} daily bars for "
                f"{', '.join(dataset.get('symbols') or [])} from {dataset.get('source', '')}."
            ),
            "href": "/datasets",
        }
    if name == "create_strategy":
        strategy = result.get("strategy") or {}
        return {
            "summary": f"Created strategy {strategy.get('name', '')}.",
            "href": f"/strategies/{strategy.get('id', '')}" if strategy.get("id") else "",
        }
    if name == "update_strategy_code":
        strategy = result.get("strategy") or {}
        return {
            "summary": (
                f"Updated strategy {strategy.get('name', '')} "
                f"to v{strategy.get('version', '')}."
            ),
            "href": f"/strategies/{strategy.get('id', '')}" if strategy.get("id") else "",
        }
    if name == "run_backtest":
        run = result.get("run") or {}
        metrics = run.get("metrics") or {}
        parts = [f"Run {str(run.get('id', ''))[:8]} {run.get('status', '')}"]
        if isinstance(metrics.get("total_return"), int | float):
            parts.append(f"return {metrics['total_return'] * 100:.2f}%")
        if isinstance(metrics.get("sharpe_ratio"), int | float):
            parts.append(f"Sharpe {metrics['sharpe_ratio']:.2f}")
        if run.get("error"):
            parts.append(str(run["error"]))
        return {
            "summary": ", ".join(parts) + ".",
            "href": f"/runs/{run.get('id', '')}" if run.get("id") else "",
        }
    return {"summary": "Done.", "href": ""}


# --- handlers -------------------------------------------------------------------------


async def _list_strategies(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    limit = _int_arg(args, "limit", 20, 1, 50)
    items, total = await strategy_service.list_strategies(db, limit=limit, offset=0)
    return {
        "total": total,
        "items": [
            {
                "id": str(strategy.id),
                "name": strategy.name,
                "description": strategy.description,
                "version": strategy.version,
                "updated_at": _iso(strategy.updated_at),
            }
            for strategy in items
        ],
    }


async def _get_strategy(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    strategy = await strategy_service.get_strategy(db, _uuid_arg(args, "strategy_id"))
    if strategy is None:
        raise ToolExecutionError("Strategy not found")
    return {"strategy": chat_context_service.strategy_payload(strategy)}


async def _list_runs(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    strategy_id = _uuid_arg(args, "strategy_id", required=False)
    limit = _int_arg(args, "limit", 10, 1, 50)
    items, total = await run_service.list_runs(db, strategy_id, limit=limit, offset=0)
    return {
        "total": total,
        "items": [
            {
                "id": str(run.id),
                "strategy_id": str(run.strategy_id),
                "dataset_id": str(run.dataset_id) if run.dataset_id else None,
                "status": run.status,
                "params": run.params or {},
                "metrics": _headline_metrics(run.metrics or {}),
                "error": run.error,
                "created_at": _iso(run.created_at),
                "completed_at": _iso(run.completed_at),
            }
            for run in items
        ],
    }


async def _get_run(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    run_id = _uuid_arg(args, "run_id")
    context = await chat_context_service.build_prompt_context(
        db, {"type": "run", "run_id": str(run_id)}
    )
    run = await run_service.get_run(db, run_id)
    if run is not None and run.dataset_id is not None:
        dataset = await dataset_service.get_dataset(db, run.dataset_id)
        if dataset is not None:
            context["dataset"] = market_data_service.dataset_payload(dataset)
    return context


async def _compare_runs(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    raw_ids = args.get("run_ids")
    if not isinstance(raw_ids, list) or len(raw_ids) < 2:
        raise ToolExecutionError("run_ids must list at least two run UUIDs")
    return await chat_context_service.build_prompt_context(
        db,
        {"type": "compare", "run_ids": [str(_parse_uuid(value, "run_ids")) for value in raw_ids]},
    )


async def _list_datasets(db: AsyncSession, _args: dict[str, Any]) -> dict[str, Any]:
    items, total = await dataset_service.list_datasets(db, limit=100, offset=0)
    return {"total": total, "items": [market_data_service.dataset_payload(d) for d in items]}


async def _fetch_market_data(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    symbol = args.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ToolExecutionError("symbol is required")
    dataset = await market_data_service.fetch_and_register(
        db,
        symbol,
        _date_arg(args, "start_date"),
        _date_arg(args, "end_date"),
    )
    return {"dataset": market_data_service.dataset_payload(dataset)}


async def _create_strategy(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    name = args.get("name")
    code = args.get("code")
    if not isinstance(name, str) or not name.strip():
        raise ToolExecutionError("name is required")
    if not isinstance(code, str) or not code.strip():
        raise ToolExecutionError("code is required")
    description = args.get("description") if isinstance(args.get("description"), str) else ""
    strategy = await strategy_service.create_strategy(
        db, StrategyCreate(name=name.strip(), description=description or "", code=code)
    )
    return {"strategy": _strategy_summary(strategy)}


async def _update_strategy_code(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    code = args.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ToolExecutionError("code is required")
    strategy = await strategy_service.update_strategy(
        db, _uuid_arg(args, "strategy_id"), StrategyUpdate(code=code)
    )
    if strategy is None:
        raise ToolExecutionError("Strategy not found")
    return {"strategy": _strategy_summary(strategy)}


async def _run_backtest(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    strategy_id = _uuid_arg(args, "strategy_id")
    strategy = await strategy_service.get_strategy(db, strategy_id)
    if strategy is None:
        raise ToolExecutionError("Strategy not found")

    params = args.get("params") or {}
    if not isinstance(params, dict):
        raise ToolExecutionError("params must be an object")

    dataset = None
    dataset_id = _uuid_arg(args, "dataset_id", required=False)
    if dataset_id is not None:
        dataset = await dataset_service.get_dataset(db, dataset_id)
        if dataset is None:
            raise ToolExecutionError("Dataset not found")
    elif isinstance(params.get("symbol"), str):
        dataset = await _find_dataset_for_symbol(db, params["symbol"])

    run = await run_service.create_run(
        db,
        RunCreate(
            strategy_id=strategy_id, params=params, dataset_id=dataset.id if dataset else None
        ),
        dataset=dataset,
    )
    await job_service.enqueue_backtest(run.id)
    run = await wait_for_run(db, run, settings.chat_tool_run_timeout_seconds)

    payload = chat_context_service.run_payload(run)
    payload["dataset"] = market_data_service.dataset_payload(dataset) if dataset else None
    if run.status not in TERMINAL_RUN_STATUSES:
        payload["note"] = (
            "The run is still in progress. Call get_run with this run id to fetch final results."
        )
    return {"run": payload}


async def wait_for_run(db: AsyncSession, run: Any, timeout_seconds: float) -> Any:
    deadline = asyncio.get_running_loop().time() + max(0.0, timeout_seconds)
    while run.status not in TERMINAL_RUN_STATUSES and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(RUN_POLL_INTERVAL_SECONDS)
        await db.refresh(run)
    return run


async def _find_dataset_for_symbol(db: AsyncSession, symbol: str) -> Any:
    items, _ = await dataset_service.list_datasets(db, limit=100, offset=0)
    wanted = symbol.strip().upper()
    matches = [d for d in items if wanted in [s.upper() for s in (d.symbols or [])]]
    if not matches:
        return None
    # Prefer real data over the synthetic sample files when both exist.
    real = [d for d in matches if (getattr(d, "source", "") or "") != "synthetic"]
    return (real or matches)[0]


_HANDLERS = {
    "list_strategies": _list_strategies,
    "get_strategy": _get_strategy,
    "list_runs": _list_runs,
    "get_run": _get_run,
    "compare_runs": _compare_runs,
    "list_datasets": _list_datasets,
    "fetch_market_data": _fetch_market_data,
    "create_strategy": _create_strategy,
    "update_strategy_code": _update_strategy_code,
    "run_backtest": _run_backtest,
}


# --- helpers --------------------------------------------------------------------------


def _strategy_summary(strategy: Any) -> dict[str, Any]:
    return {
        "id": str(strategy.id),
        "name": strategy.name,
        "description": strategy.description,
        "version": strategy.version,
        "updated_at": _iso(strategy.updated_at),
    }


def _headline_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = ("total_return", "sharpe_ratio", "max_drawdown", "total_trades", "win_rate")
    return {key: metrics[key] for key in keys if key in metrics}


def _parse_uuid(value: Any, field: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if not isinstance(value, str):
        raise ToolExecutionError(f"{field} must be a UUID string")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ToolExecutionError(f"{field} must be a valid UUID") from exc


def _uuid_arg(args: dict[str, Any], field: str, required: bool = True) -> Any:
    value = args.get(field)
    if value in (None, ""):
        if required:
            raise ToolExecutionError(f"{field} is required")
        return None
    return _parse_uuid(value, field)


def _int_arg(args: dict[str, Any], field: str, default: int, minimum: int, maximum: int) -> int:
    value = args.get(field, default)
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError(f"{field} must be an integer") from exc
    return max(minimum, min(maximum, number))


def _date_arg(args: dict[str, Any], field: str) -> date | None:
    value = args.get(field)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ToolExecutionError(f"{field} must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ToolExecutionError(f"{field} must be a YYYY-MM-DD string") from exc


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
