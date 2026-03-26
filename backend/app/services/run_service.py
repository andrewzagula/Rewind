import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run
from app.models.trade import Trade
from app.schemas.run import RunCreate


async def create_run(db: AsyncSession, data: RunCreate) -> Run:
    run = Run(
        strategy_id=data.strategy_id,
        params=data.params,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def get_run(db: AsyncSession, run_id: uuid.UUID) -> Run | None:
    return await db.get(Run, run_id)


async def list_runs(
    db: AsyncSession,
    strategy_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Run], int]:
    base = select(Run)
    count_q = select(func.count()).select_from(Run)
    if strategy_id is not None:
        base = base.where(Run.strategy_id == strategy_id)
        count_q = count_q.where(Run.strategy_id == strategy_id)
    total = await db.scalar(count_q)
    result = await db.execute(
        base.order_by(Run.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total or 0


async def get_run_trades(
    db: AsyncSession,
    run_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Trade], int]:
    count_q = select(func.count()).select_from(Trade).where(Trade.run_id == run_id)
    total = await db.scalar(count_q)
    result = await db.execute(
        select(Trade)
        .where(Trade.run_id == run_id)
        .order_by(Trade.timestamp)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total or 0
