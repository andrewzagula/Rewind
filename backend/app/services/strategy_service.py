"""Strategy CRUD operations."""

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import Strategy
from app.schemas.strategy import StrategyCreate, StrategyUpdate


async def create_strategy(db: AsyncSession, data: StrategyCreate) -> Strategy:
    strategy = Strategy(**data.model_dump())
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return strategy


async def get_strategy(db: AsyncSession, strategy_id: uuid.UUID) -> Strategy | None:
    return await db.get(Strategy, strategy_id)


async def list_strategies(
    db: AsyncSession, limit: int = 20, offset: int = 0
) -> tuple[list[Strategy], int]:
    total = await db.scalar(select(func.count()).select_from(Strategy))
    result = await db.execute(
        select(Strategy).order_by(Strategy.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total or 0


async def update_strategy(
    db: AsyncSession, strategy_id: uuid.UUID, data: StrategyUpdate
) -> Strategy | None:
    strategy = await db.get(Strategy, strategy_id)
    if strategy is None:
        return None
    updates = data.model_dump(exclude_unset=True)
    if updates:
        if "code" in updates:
            strategy.version += 1
        for key, value in updates.items():
            setattr(strategy, key, value)
        await db.commit()
        await db.refresh(strategy)
    return strategy


async def delete_strategy(db: AsyncSession, strategy_id: uuid.UUID) -> bool:
    strategy = await db.get(Strategy, strategy_id)
    if strategy is None:
        return False
    await db.delete(strategy)
    await db.commit()
    return True
