import logging
import multiprocessing
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty
from typing import Any

from arq.connections import RedisSettings

from app.core.config import settings
from app.core.database import async_session
from app.models.run import Run
from app.models.strategy import Strategy
from app.models.trade import Trade

logger = logging.getLogger(__name__)

BACKTEST_TIMEOUT_SECONDS = 15
DATA_DIR = next(
    (
        candidate
        for candidate in (
            Path(__file__).resolve().parent / "data" / "sample",
            Path(__file__).resolve().parent.parent / "data" / "sample",
            Path.cwd() / "data" / "sample",
            Path.cwd().parent / "data" / "sample",
        )
        if candidate.exists()
    ),
    Path(__file__).resolve().parent.parent / "data" / "sample",
)


def _add_repo_roots_to_path() -> None:
    current = Path(__file__).resolve()
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        current.parent,
        current.parent.parent,
    ]
    for candidate in candidates:
        if (candidate / "engine" / "strategy_runner.py").exists():
            candidate_str = str(candidate)
            if candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)


def _execute_backtest_payload(
    strategy_code: str,
    params: dict[str, Any],
    symbol: str,
    timeframe: str,
    initial_cash: float,
    data_dir: str,
) -> dict[str, Any]:
    _add_repo_roots_to_path()

    from engine.data_loader import load_bars
    from engine.executor import run_backtest as execute
    from engine.strategy_runner import load_strategy_class

    strategy_cls = load_strategy_class(strategy_code)
    strategy_instance = strategy_cls()
    bars = load_bars(symbol, timeframe, data_dir=Path(data_dir))
    result = execute(
        strategy=strategy_instance,
        data=bars,
        params=params,
        initial_cash=initial_cash,
    )
    return {
        "metrics": result.metrics,
        "equity_curve": result.equity_curve,
        "equity_points": result.equity_points,
        "trades": result.trades,
    }


def _execute_backtest_child(
    queue: multiprocessing.Queue,
    strategy_code: str,
    params: dict[str, Any],
    symbol: str,
    timeframe: str,
    initial_cash: float,
    data_dir: str,
) -> None:
    try:
        queue.put(
            {
                "ok": True,
                "result": _execute_backtest_payload(
                    strategy_code,
                    params,
                    symbol,
                    timeframe,
                    initial_cash,
                    data_dir,
                ),
            }
        )
    except Exception as exc:
        queue.put({"ok": False, "error": str(exc)})


def execute_backtest_with_timeout(
    strategy_code: str,
    params: dict[str, Any],
    symbol: str,
    timeframe: str,
    initial_cash: float,
    data_dir: Path = DATA_DIR,
    timeout_seconds: float = BACKTEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    queue: multiprocessing.Queue = multiprocessing.Queue(maxsize=1)
    process = multiprocessing.Process(
        target=_execute_backtest_child,
        args=(
            queue,
            strategy_code,
            params,
            symbol,
            timeframe,
            initial_cash,
            str(data_dir),
        ),
        daemon=True,
    )
    process.start()
    deadline = time.monotonic() + timeout_seconds
    payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            payload = queue.get(timeout=0.05)
            break
        except Empty:
            if not process.is_alive():
                process.join()
                try:
                    payload = queue.get_nowait()
                except Empty:
                    payload = None
                break

    if payload is None:
        if process.is_alive():
            process.terminate()
            process.join(1)
            raise TimeoutError(
                f"Strategy execution timed out after {timeout_seconds:g} seconds."
            )
        raise RuntimeError(
            "Strategy execution failed without returning a result "
            f"(exit code {process.exitcode})."
        )

    process.join(1)

    if not payload["ok"]:
        raise RuntimeError(payload["error"])

    return payload["result"]


async def run_backtest(ctx: dict, run_id: str) -> dict:
    async with async_session() as db:
        run = await db.get(Run, uuid.UUID(run_id))
        if run is None:
            logger.error("Run %s not found", run_id)
            return {"run_id": run_id, "status": "failed", "error": "Run not found"}

        run.status = "running"
        run.started_at = datetime.now(UTC)
        await db.commit()

        try:
            strategy_model = await db.get(Strategy, run.strategy_id)
            if strategy_model is None:
                raise ValueError(f"Strategy {run.strategy_id} not found")

            symbol = run.params.get("symbol", "AAPL")
            timeframe = run.params.get("timeframe", "1d")
            result = execute_backtest_with_timeout(
                strategy_code=strategy_model.code,
                params=run.params,
                symbol=symbol,
                timeframe=timeframe,
                initial_cash=run.params.get("initial_cash", 100_000.0),
            )

            for t in result["trades"]:
                trade = Trade(
                    run_id=run.id,
                    symbol=t["symbol"],
                    side=t["side"],
                    quantity=t["quantity"],
                    price=t["price"],
                    timestamp=t.get("timestamp", datetime.now(UTC)),
                    pnl=t.get("pnl", 0),
                )
                db.add(trade)

            run.status = "completed"
            run.metrics = result["metrics"]
            run.artifacts = {
                "equity_curve": result["equity_curve"],
                "equity_points": result["equity_points"],
            }
            run.completed_at = datetime.now(UTC)
            await db.commit()

            logger.info("Run %s completed: %s", run_id, result["metrics"])
            return {"run_id": run_id, "status": "completed"}

        except Exception as e:
            logger.exception("Run %s failed", run_id)
            run.status = "failed"
            run.error = str(e)
            run.completed_at = datetime.now(UTC)
            await db.commit()
            return {"run_id": run_id, "status": "failed", "error": str(e)}


class WorkerSettings:
    functions = [run_backtest]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
