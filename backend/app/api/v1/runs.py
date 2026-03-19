from fastapi import APIRouter

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("")
async def create_run() -> dict[str, str]:
    return {"status": "not implemented"}


@router.get("")
async def list_runs() -> dict[str, list]:
    return {"runs": []}


@router.get("/{run_id}")
async def get_run(run_id: str) -> dict[str, str]:
    return {"run_id": run_id, "status": "not implemented"}
