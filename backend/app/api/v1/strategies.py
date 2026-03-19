from fastapi import APIRouter

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("")
async def create_strategy() -> dict[str, str]:
    return {"status": "not implemented"}


@router.get("")
async def list_strategies() -> dict[str, list]:
    return {"strategies": []}


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str) -> dict[str, str]:
    return {"strategy_id": strategy_id, "status": "not implemented"}
