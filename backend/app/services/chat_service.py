import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_session import ChatSession
from app.models.message import Message
from app.schemas.chat import (
    ChatActionAuditStatus,
    ChatMessageResponse,
    ChatRequest,
    ChatRole,
    ChatSessionResponse,
    ChatSessionSummary,
)

MessageRole = Literal["user", "assistant", "system"]


def message_response(message: Message) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        session_id=message.session_id,
        role=cast(ChatRole, message.role),
        content=message.content,
        linked_run_id=message.linked_run_id,
        metadata=message.metadata_,
        ordering=message.ordering,
        created_at=message.created_at,
    )


def session_summary(
    session: ChatSession,
    message_count: int = 0,
    last_message_at: datetime | None = None,
) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=session.id,
        context=session.context,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=message_count,
        last_message_at=last_message_at,
    )


async def get_or_create_session(db: AsyncSession, data: ChatRequest) -> ChatSession | None:
    if data.session_id is not None:
        session = await db.get(ChatSession, data.session_id)
        if session is None:
            return None
        if data.context:
            session.context = data.context
            session.updated_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(session)
        return session

    session = ChatSession(context=data.context)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def append_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: MessageRole,
    content: str,
    linked_run_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> Message:
    max_order = await db.scalar(
        select(func.max(Message.ordering)).where(Message.session_id == session_id)
    )
    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        linked_run_id=linked_run_id,
        metadata_=metadata or {},
        ordering=(max_order or 0) + 1,
    )
    db.add(message)

    session = await db.get(ChatSession, session_id)
    if session is not None:
        session.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(message)
    return message


async def record_assistant_action(
    db: AsyncSession,
    message_id: uuid.UUID,
    action_id: uuid.UUID,
    status: ChatActionAuditStatus,
    result: dict[str, Any] | None = None,
    error: str = "",
) -> Message | None:
    message = await db.get(Message, message_id)
    if message is None or message.role != "assistant":
        return None

    metadata = dict(message.metadata_ or {})
    actions = metadata.get("assistant_actions")
    if not isinstance(actions, list):
        return None

    completed_at = datetime.now(UTC).isoformat()
    found_action = False
    updated_actions: list[Any] = []
    for action in actions:
        if not isinstance(action, dict) or str(action.get("id")) != str(action_id):
            updated_actions.append(action)
            continue

        found_action = True
        updated_action = dict(action)
        updated_action["status"] = status
        updated_action["completed_at"] = completed_at
        updated_action["result"] = result or {}
        if error:
            updated_action["error"] = error
        else:
            updated_action.pop("error", None)
        updated_actions.append(updated_action)

    if not found_action:
        return None

    metadata["assistant_actions"] = updated_actions
    message.metadata_ = metadata

    session = await db.get(ChatSession, message.session_id)
    if session is not None:
        session.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(message)
    return message


async def list_messages(db: AsyncSession, session_id: uuid.UUID) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.ordering.asc(), Message.created_at.asc(), Message.id.asc())
    )
    return list(result.scalars().all())


async def get_session_summary(
    db: AsyncSession, session_id: uuid.UUID
) -> ChatSessionSummary | None:
    session = await db.get(ChatSession, session_id)
    if session is None:
        return None

    message_count = await db.scalar(
        select(func.count()).select_from(Message).where(Message.session_id == session_id)
    )
    last_message_at = await db.scalar(
        select(func.max(Message.created_at)).where(Message.session_id == session_id)
    )
    return session_summary(session, int(message_count or 0), last_message_at)


async def list_sessions(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[ChatSessionSummary], int]:
    total = await db.scalar(select(func.count()).select_from(ChatSession))
    stats = (
        select(
            Message.session_id.label("session_id"),
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .group_by(Message.session_id)
        .subquery()
    )
    result = await db.execute(
        select(
            ChatSession,
            func.coalesce(stats.c.message_count, 0),
            stats.c.last_message_at,
        )
        .outerjoin(stats, ChatSession.id == stats.c.session_id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    items = [
        session_summary(session, int(message_count or 0), last_message_at)
        for session, message_count, last_message_at in result.all()
    ]
    return items, int(total or 0)


async def get_session_detail(
    db: AsyncSession, session_id: uuid.UUID
) -> ChatSessionResponse | None:
    session = await db.get(ChatSession, session_id)
    if session is None:
        return None

    messages = await list_messages(db, session_id)
    responses = [message_response(message) for message in messages]
    last_message_at = responses[-1].created_at if responses else None

    return ChatSessionResponse(
        **session_summary(session, len(responses), last_message_at).model_dump(),
        messages=responses,
    )


async def delete_session(db: AsyncSession, session_id: uuid.UUID) -> bool:
    session = await db.get(ChatSession, session_id)
    if session is None:
        return False

    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return True
