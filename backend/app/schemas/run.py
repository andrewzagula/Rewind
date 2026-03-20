import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class RunCreate(BaseModel):
    strategy_id: uuid.UUID
    params: dict = {}
    dataset_id: uuid.UUID | None = None


class RunResponse(BaseModel):
    id: uuid.UUID
    strategy_id: uuid.UUID
    params: dict
    metrics: dict
    artifacts: dict = {}
    status: str
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TradeResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    timestamp: datetime
    pnl: Decimal

    model_config = {"from_attributes": True}
