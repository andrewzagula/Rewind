import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChatRole = Literal["user", "assistant", "system"]
ChatStreamEventType = Literal["session", "chunk", "done", "error"]
ChatActionAuditStatus = Literal["completed", "failed", "cancelled"]


class RunChatContext(BaseModel):
    type: Literal["run"]
    run_id: uuid.UUID


class CompareChatContext(BaseModel):
    type: Literal["compare"]
    run_ids: list[uuid.UUID] = Field(min_length=2)


ChatContextSelector = RunChatContext | CompareChatContext


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class ChatChunk(BaseModel):
    type: Literal["text", "code", "action"]
    content: str


class ChatActionAuditRequest(BaseModel):
    status: ChatActionAuditStatus
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: ChatRole
    content: str
    linked_run_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    ordering: int
    created_at: datetime


class ChatSessionSummary(BaseModel):
    id: uuid.UUID
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatSessionResponse(ChatSessionSummary):
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatStreamEvent(BaseModel):
    type: ChatStreamEventType
    session: ChatSessionSummary | None = None
    message: ChatMessageResponse | None = None
    content: str = ""
    error: str = ""
