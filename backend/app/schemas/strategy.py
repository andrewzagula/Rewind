import uuid
from datetime import datetime

from pydantic import BaseModel


class StrategyCreate(BaseModel):
    name: str
    description: str = ""
    code: str


class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    code: str | None = None


class StrategyResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    code: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
