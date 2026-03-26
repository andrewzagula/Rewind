import uuid
from typing import Literal

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str
    context: dict = {}


class ChatChunk(BaseModel):
    type: Literal["text", "code", "action"]
    content: str
