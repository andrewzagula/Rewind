import uuid

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import DbSession
from app.schemas.run import CompareResponse
from app.services import compare_service

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("", response_model=CompareResponse)
async def compare_runs(
    db: DbSession,
    run_ids: str = Query(..., description="Comma-separated run UUIDs to compare"),
) -> CompareResponse:
    try:
        parsed_run_ids = [
            uuid.UUID(raw_run_id.strip())
            for raw_run_id in run_ids.split(",")
            if raw_run_id.strip()
        ]
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="run_ids must be comma-separated UUIDs",
        ) from exc

    try:
        return await compare_service.compare_runs(db, parsed_run_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except compare_service.MissingRunsError as exc:
        missing = ", ".join(str(run_id) for run_id in exc.missing_ids)
        raise HTTPException(status_code=404, detail=f"Runs not found: {missing}") from exc
