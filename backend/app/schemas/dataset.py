import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class DatasetCreate(BaseModel):
    name: str
    symbols: list[str]
    timeframe: str
    start_date: date
    end_date: date
    file_path: str


class DatasetFetchRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=15)
    start_date: date | None = None
    end_date: date | None = None


class DatasetResponse(BaseModel):
    id: uuid.UUID
    name: str
    symbols: list[str]
    timeframe: str
    start_date: date
    end_date: date
    row_count: int
    file_path: str
    checksum: str
    source: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}
