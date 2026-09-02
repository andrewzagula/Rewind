import uuid

from fastapi import APIRouter, HTTPException

from app.core.deps import DbSession
from app.schemas.dataset import DatasetFetchRequest, DatasetResponse
from app.services import dataset_service, market_data_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=dict)
async def list_datasets(
    db: DbSession,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    items, total = await dataset_service.list_datasets(db, limit, offset)
    return {"items": [DatasetResponse.model_validate(dataset) for dataset in items], "total": total}


@router.post("/fetch", response_model=DatasetResponse, status_code=201)
async def fetch_dataset(data: DatasetFetchRequest, db: DbSession) -> DatasetResponse:
    """Download real daily bars for a symbol, store them as Parquet, and register a dataset."""
    try:
        dataset = await market_data_service.fetch_and_register(
            db, data.symbol, data.start_date, data.end_date
        )
    except market_data_service.MarketDataValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except market_data_service.MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return DatasetResponse.model_validate(dataset)


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(dataset_id: uuid.UUID, db: DbSession) -> DatasetResponse:
    dataset = await dataset_service.get_dataset(db, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return DatasetResponse.model_validate(dataset)
