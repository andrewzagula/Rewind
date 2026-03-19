import uuid

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str
    context: dict = {}


class ChatChunk(BaseModel):
    type: str  # "text" | "code" | "action"
    content: str
