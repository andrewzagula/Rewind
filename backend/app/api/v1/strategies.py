"""Strategy CRUD endpoints."""

import uuid

from fastapi import APIRouter, HTTPException

from app.core.deps import DbSession
from app.schemas.strategy import StrategyCreate, StrategyResponse, StrategyUpdate
from app.services import strategy_service

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("", response_model=StrategyResponse, status_code=201)
async def create_strategy(data: StrategyCreate, db: DbSession) -> StrategyResponse:
    strategy = await strategy_service.create_strategy(db, data)
    return StrategyResponse.model_validate(strategy)


@router.get("", response_model=dict)
async def list_strategies(db: DbSession, limit: int = 20, offset: int = 0) -> dict:
    items, total = await strategy_service.list_strategies(db, limit, offset)
    return {"items": [StrategyResponse.model_validate(s) for s in items], "total": total}


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(strategy_id: uuid.UUID, db: DbSession) -> StrategyResponse:
    strategy = await strategy_service.get_strategy(db, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return StrategyResponse.model_validate(strategy)


@router.patch("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: uuid.UUID, data: StrategyUpdate, db: DbSession
) -> StrategyResponse:
    strategy = await strategy_service.update_strategy(db, strategy_id, data)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return StrategyResponse.model_validate(strategy)


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(strategy_id: uuid.UUID, db: DbSession) -> None:
    deleted = await strategy_service.delete_strategy(db, strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found")
