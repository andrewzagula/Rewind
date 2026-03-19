from fastapi import APIRouter

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
async def list_datasets() -> dict[str, list]:
    return {"datasets": []}
