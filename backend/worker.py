import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from arq.connections import RedisSettings

from app.core.config import settings
from app.core.database import async_session
from app.models.run import Run
from app.models.strategy import Strategy
from app.models.trade import Trade

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


async def run_backtest(ctx: dict, run_id: str) -> dict:
    from engine.data_loader import load_bars
    from engine.executor import run_backtest as execute
    from engine.strategy_runner import load_strategy_class

    async with async_session() as db:
        run = await db.get(Run, uuid.UUID(run_id))
        if run is None:
            logger.error("Run %s not found", run_id)
            return {"run_id": run_id, "status": "failed", "error": "Run not found"}

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            strategy_model = await db.get(Strategy, run.strategy_id)
            if strategy_model is None:
                raise ValueError(f"Strategy {run.strategy_id} not found")

            strategy_cls = load_strategy_class(strategy_model.code)
            strategy_instance = strategy_cls()

            symbol = run.params.get("symbol", "AAPL")
            timeframe = run.params.get("timeframe", "1d")
            bars = load_bars(symbol, timeframe, data_dir=DATA_DIR)

            result = execute(
                strategy=strategy_instance,
                data=bars,
                params=run.params,
                initial_cash=run.params.get("initial_cash", 100_000.0),
            )

            for t in result.trades:
                trade = Trade(
                    run_id=run.id,
                    symbol=t["symbol"],
                    side=t["side"],
                    quantity=t["quantity"],
                    price=t["price"],
                    timestamp=t.get("timestamp", datetime.now(timezone.utc)),
                    pnl=t.get("pnl", 0),
                )
                db.add(trade)

            run.status = "completed"
            run.metrics = result.metrics
            run.artifacts = {
                "equity_curve": result.equity_curve,
                "equity_points": result.equity_points,
            }
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info("Run %s completed: %s", run_id, result.metrics)
            return {"run_id": run_id, "status": "completed"}

        except Exception as e:
            logger.exception("Run %s failed", run_id)
            run.status = "failed"
            run.error = str(e)
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {"run_id": run_id, "status": "failed", "error": str(e)}


class WorkerSettings:
    functions = [run_backtest]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
