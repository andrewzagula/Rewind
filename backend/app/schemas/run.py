import uuid
from datetime import datetime

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
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
