"""Arq worker entry point. Run with: arq backend.worker.WorkerSettings"""

from arq.connections import RedisSettings

from app.core.config import settings


async def run_backtest(ctx: dict, run_id: str) -> dict:
    """Execute a backtest run. Picked up from Redis queue."""
    # TODO: Load strategy, load data, execute, store results
    return {"run_id": run_id, "status": "completed"}


class WorkerSettings:
    functions = [run_backtest]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
