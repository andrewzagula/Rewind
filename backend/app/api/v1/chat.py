from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def send_message() -> dict[str, str]:
    return {"status": "not implemented"}


@router.get("/sessions")
async def list_sessions() -> dict[str, list]:
    return {"sessions": []}
