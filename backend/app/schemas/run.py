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


class CompareEquityPoint(BaseModel):
    index: int
    timestamp: str = ""
    value: float


class ComparedRun(BaseModel):
    id: uuid.UUID
    strategy_id: uuid.UUID
    status: str
    params: dict
    metrics: dict
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    equity_points: list[CompareEquityPoint]


class MetricDelta(BaseModel):
    key: str
    base: float | None
    values: list[float | None]
    deltas: list[float | None]


class CompareResponse(BaseModel):
    runs: list[ComparedRun]
    metric_deltas: list[MetricDelta]


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
