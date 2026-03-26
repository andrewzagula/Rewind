import uuid

from arq.connections import ArqRedis, create_pool, RedisSettings
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.deps import DbSession
from app.schemas.run import RunCreate, RunResponse, TradeResponse
from app.services import run_service, strategy_service

router = APIRouter(prefix="/runs", tags=["runs"])


async def _get_arq_pool() -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))


@router.post("", response_model=RunResponse, status_code=201)
async def create_run(data: RunCreate, db: DbSession) -> RunResponse:
    strategy = await strategy_service.get_strategy(db, data.strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    run = await run_service.create_run(db, data)

    pool = await _get_arq_pool()
    await pool.enqueue_job("run_backtest", str(run.id))
    await pool.aclose()

    return RunResponse.model_validate(run)


@router.get("", response_model=dict)
async def list_runs(
    db: DbSession,
    strategy_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    items, total = await run_service.list_runs(db, strategy_id, limit, offset)
    return {"items": [RunResponse.model_validate(r) for r in items], "total": total}


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: uuid.UUID, db: DbSession) -> RunResponse:
    run = await run_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse.model_validate(run)


@router.get("/{run_id}/trades", response_model=dict)
async def get_run_trades(
    run_id: uuid.UUID,
    db: DbSession,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    run = await run_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    trades, total = await run_service.get_run_trades(db, run_id, limit, offset)
    return {"items": [TradeResponse.model_validate(t) for t in trades], "total": total}
