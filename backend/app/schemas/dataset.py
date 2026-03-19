import uuid
from datetime import date, datetime

from pydantic import BaseModel


class DatasetCreate(BaseModel):
    name: str
    symbols: list[str]
    timeframe: str
    start_date: date
    end_date: date
    file_path: str


class DatasetResponse(BaseModel):
    id: uuid.UUID
    name: str
    symbols: list[str]
    timeframe: str
    start_date: date
    end_date: date
    row_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
