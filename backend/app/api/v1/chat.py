from __future__ import annotations

import json
import sys
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.deps import DbSession
from app.schemas.chat import (
    ChatActionAuditRequest,
    ChatMessageResponse,
    ChatRequest,
    ChatSessionResponse,
    ChatStreamEvent,
)
from app.services import chat_context_service, chat_service

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_HISTORY_MESSAGES = 24


class StreamingLLMClient(Protocol):
    def chat(
        self, messages: list[dict[str, str]], stream: bool = True
    ) -> AsyncGenerator[str]:
        ...


def _prompt_candidates() -> list[Path]:
    current = Path(__file__).resolve()
    return [
        Path.cwd() / "llm" / "prompts" / "system.txt",
        current.parents[3] / "llm" / "prompts" / "system.txt",
        current.parents[4] / "llm" / "prompts" / "system.txt",
    ]


def _load_system_prompt() -> str:
    for path in _prompt_candidates():
        if path.exists():
            return path.read_text()

    return (
        "You are Rewind, an AI research assistant for quantitative trading strategies.\n\n"
        "CONTEXT (injected per request):\n{context}"
    )


def _build_llm_messages(
    history: list[ChatMessageResponse],
    context: dict[str, Any],
) -> list[dict[str, str]]:
    system_prompt = _load_system_prompt().replace("{context}", _format_prompt_context(context))
    messages = [{"role": "system", "content": system_prompt}]
    for message in history[-MAX_HISTORY_MESSAGES:]:
        if message.role in {"user", "assistant"}:
            messages.append({"role": message.role, "content": message.content})
    return messages


def _format_prompt_context(context: dict[str, Any]) -> str:
    try:
        from llm.context import format_prompt_context
    except ModuleNotFoundError:
        if not context:
            return "No additional context was provided."
        return (
            "Use only the trusted Rewind context below. If needed fields are missing, "
            "state that limitation explicitly instead of inferring values.\n\n"
            f"```json\n{json.dumps(context, indent=2, sort_keys=True, default=str)}\n```"
        )

    return format_prompt_context(context)


def _get_llm_client() -> StreamingLLMClient:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    from llm.client import LLMClient

    return LLMClient(api_key=settings.openai_api_key)


def _llm_module_roots() -> list[Path]:
    current = Path(__file__).resolve()
    return [
        Path.cwd(),
        Path.cwd().parent,
        current.parents[4],
    ]


def _load_llm_parser_symbol(name: str) -> Callable[..., Any] | None:
    try:
        import llm.parser as parser

        return getattr(parser, name)
    except (AttributeError, ModuleNotFoundError):
        for root in _llm_module_roots():
            if (root / "llm" / "parser.py").exists() and str(root) not in sys.path:
                sys.path.insert(0, str(root))

    try:
        import llm.parser as parser

        return getattr(parser, name)
    except (AttributeError, ModuleNotFoundError):
        return None


def _assistant_message_metadata(
    base_metadata: dict[str, Any], assistant_content: str
) -> dict[str, Any]:
    assistant_metadata = dict(base_metadata)
    validate_generated_strategy_response = _load_llm_parser_symbol(
        "validate_generated_strategy_response"
    )
    parse_assistant_actions = _load_llm_parser_symbol("parse_assistant_actions")

    generated_strategy = None
    if validate_generated_strategy_response is None:
        return assistant_metadata
    generated_strategy = validate_generated_strategy_response(assistant_content)
    if generated_strategy is not None:
        assistant_metadata["generated_strategy"] = {
            "code": generated_strategy.code,
            "valid": generated_strategy.valid,
            "class_name": generated_strategy.class_name,
            "errors": generated_strategy.errors,
        }

    if parse_assistant_actions is not None:
        action_result = parse_assistant_actions(assistant_content, generated_strategy)
        if action_result.actions:
            created_at = datetime.now(UTC).isoformat()
            assistant_metadata["assistant_actions"] = [
                {**action, "created_at": action.get("created_at") or created_at}
                for action in action_result.actions
            ]
        if action_result.errors:
            assistant_metadata["assistant_action_errors"] = action_result.errors

    return assistant_metadata


def _sse(event: ChatStreamEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


@router.post("")
async def send_message(data: ChatRequest, db: DbSession) -> StreamingResponse:
    message = data.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    request_context = _normalize_context(data.context)
    prompt_context = await _preload_prompt_context(db, request_context)
    session_data = data.model_copy(update={"context": request_context})

    session = await chat_service.get_or_create_session(db, session_data)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    effective_context = session.context or {}
    if not request_context:
        prompt_context = await _preload_prompt_context(db, effective_context)

    linked_run_id = chat_context_service.linked_run_id(effective_context)
    metadata = chat_context_service.message_metadata(effective_context)

    await chat_service.append_message(
        db,
        session.id,
        "user",
        message,
        linked_run_id=linked_run_id,
        metadata=metadata,
    )
    summary = await chat_service.get_session_summary(db, session.id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    history = [
        chat_service.message_response(history_message)
        for history_message in await chat_service.list_messages(db, session.id)
    ]
    llm_messages = _build_llm_messages(history, prompt_context)

    async def stream_events() -> AsyncGenerator[str]:
        yield _sse(ChatStreamEvent(type="session", session=summary))

        try:
            client = _get_llm_client()
            chunks: list[str] = []
            async for content in client.chat(llm_messages, stream=True):
                chunks.append(content)
                yield _sse(ChatStreamEvent(type="chunk", content=content))

            assistant_content = "".join(chunks).strip()
            if not assistant_content:
                yield _sse(
                    ChatStreamEvent(
                        type="error",
                        error="Assistant returned an empty response.",
                    )
                )
                return

            assistant = await chat_service.append_message(
                db,
                session.id,
                "assistant",
                assistant_content,
                linked_run_id=linked_run_id,
                metadata=_assistant_message_metadata(metadata, assistant_content),
            )
            yield _sse(
                ChatStreamEvent(
                    type="done",
                    message=chat_service.message_response(assistant),
                )
            )
        except Exception:
            yield _sse(
                ChatStreamEvent(
                    type="error",
                    error="Assistant failed to respond. Check provider configuration and try again.",
                )
            )

    return StreamingResponse(stream_events(), media_type="text/event-stream")


def _normalize_context(context: dict[str, Any]) -> dict[str, Any]:
    try:
        return chat_context_service.normalize_context_selector(context)
    except chat_context_service.ChatContextValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _preload_prompt_context(db: DbSession, context: dict[str, Any]) -> dict[str, Any]:
    try:
        return await chat_context_service.build_prompt_context(db, context)
    except chat_context_service.ChatContextValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except chat_context_service.ChatContextNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/messages/{message_id}/actions/{action_id}", response_model=ChatMessageResponse)
async def record_action(
    message_id: uuid.UUID,
    action_id: uuid.UUID,
    data: ChatActionAuditRequest,
    db: DbSession,
) -> ChatMessageResponse:
    message = await chat_service.record_assistant_action(
        db,
        message_id,
        action_id,
        data.status,
        result=data.result,
        error=data.error,
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Chat action not found")
    return chat_service.message_response(message)


@router.get("/sessions", response_model=dict)
async def list_sessions(db: DbSession, limit: int = 20, offset: int = 0) -> dict[str, object]:
    items, total = await chat_service.list_sessions(db, limit, offset)
    return {"items": items, "total": total}


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session(session_id: uuid.UUID, db: DbSession) -> ChatSessionResponse:
    session = await chat_service.get_session_detail(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.delete("/sessions/{session_id}", status_code=204, response_class=Response)
async def delete_session(session_id: uuid.UUID, db: DbSession) -> Response:
    deleted = await chat_service.delete_session(db, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return Response(status_code=204)
