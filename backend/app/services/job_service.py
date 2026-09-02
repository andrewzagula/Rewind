import uuid

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import settings


async def get_arq_pool() -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def enqueue_backtest(run_id: uuid.UUID | str) -> None:
    """Queue a backtest run for the Arq worker."""
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job("run_backtest", str(run_id))
    finally:
        await pool.aclose()
