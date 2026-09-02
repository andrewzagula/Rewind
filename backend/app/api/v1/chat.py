from __future__ import annotations

import json
import logging
import sys
import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import DbSession
from app.schemas.chat import (
    ChatActionAuditRequest,
    ChatMessageResponse,
    ChatRequest,
    ChatSessionResponse,
    ChatStreamEvent,
    ChatToolActivity,
)
from app.services import chat_context_service, chat_service, chat_tool_service

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 24
MAX_TOOL_ACTIVITY_HISTORY = 8


class StreamingLLMClient(Protocol):
    def chat(
        self, messages: list[dict[str, Any]], stream: bool = True
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
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for message in history[-MAX_HISTORY_MESSAGES:]:
        if message.role in {"user", "assistant"}:
            content = message.content
            if message.role == "assistant":
                content = _with_tool_activity_note(content, message.metadata)
            messages.append({"role": message.role, "content": content})
    return messages


def _with_tool_activity_note(content: str, metadata: dict[str, Any]) -> str:
    """Remind the model of the tools it ran in an earlier turn, and the ids they produced."""
    activity = metadata.get("tool_activity") if isinstance(metadata, dict) else None
    if not isinstance(activity, list) or not activity:
        return content
    lines = []
    for item in activity[-MAX_TOOL_ACTIVITY_HISTORY:]:
        if not isinstance(item, dict):
            continue
        arguments = item.get("arguments") or {}
        try:
            rendered_args = json.dumps(arguments, sort_keys=True, default=str)
        except TypeError:
            rendered_args = str(arguments)
        lines.append(f"- {item.get('name', 'tool')}({rendered_args}) -> {item.get('summary', '')}")
    if not lines:
        return content
    return f"{content}\n\n[Tool activity in this turn]\n" + "\n".join(lines)


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

    return LLMClient(api_key=settings.openai_api_key, model=settings.openai_model)


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
            conversation: list[dict[str, Any]] = list(llm_messages)
            content_parts: list[str] = []
            tool_activity: list[dict[str, Any]] = []

            for round_index in range(chat_tool_service.MAX_TOOL_ROUNDS + 1):
                assistant_turn: dict[str, Any] = {}
                if content_parts and not content_parts[-1].endswith("\n"):
                    content_parts.append("\n\n")
                    yield _sse(ChatStreamEvent(type="chunk", content="\n\n"))

                async for event in _stream_turn(client, conversation):
                    if event.get("type") == "text" and event.get("content"):
                        content_parts.append(str(event["content"]))
                        yield _sse(ChatStreamEvent(type="chunk", content=str(event["content"])))
                    elif event.get("type") == "turn_end":
                        assistant_turn = event.get("message") or {}

                tool_calls = assistant_turn.get("tool_calls") or []
                if not tool_calls or round_index == chat_tool_service.MAX_TOOL_ROUNDS:
                    break

                conversation.append(assistant_turn)
                for call in tool_calls:
                    activity, tool_message = await _run_tool_call(db, call, tool_activity)
                    yield activity[0]
                    yield activity[1]
                    conversation.append(tool_message)

            assistant_content = "".join(content_parts).strip()
            if not assistant_content and tool_activity:
                assistant_content = _fallback_tool_summary(tool_activity)
            if not assistant_content:
                yield _sse(
                    ChatStreamEvent(
                        type="error",
                        error="Assistant returned an empty response.",
                    )
                )
                return

            assistant_metadata = _assistant_message_metadata(metadata, assistant_content)
            if tool_activity:
                assistant_metadata["tool_activity"] = tool_activity
            assistant = await chat_service.append_message(
                db,
                session.id,
                "assistant",
                assistant_content,
                linked_run_id=linked_run_id,
                metadata=assistant_metadata,
            )
            yield _sse(
                ChatStreamEvent(
                    type="done",
                    message=chat_service.message_response(assistant),
                )
            )
        except Exception:
            logger.exception("Chat stream failed")
            yield _sse(
                ChatStreamEvent(
                    type="error",
                    error=(
                        "Assistant failed to respond. "
                        "Check provider configuration and try again."
                    ),
                )
            )

    return StreamingResponse(stream_events(), media_type="text/event-stream")


async def _stream_turn(
    client: Any, conversation: list[dict[str, Any]]
) -> AsyncGenerator[dict[str, Any]]:
    """Stream one assistant turn, using tools when the client supports them."""
    stream_turn = getattr(client, "stream_turn", None)
    if stream_turn is not None:
        async for event in stream_turn(conversation, chat_tool_service.TOOL_DEFINITIONS):
            yield event
        return

    # Legacy text-only clients: adapt to the turn protocol without tool calls.
    parts: list[str] = []
    async for content in client.chat(conversation, stream=True):
        parts.append(content)
        yield {"type": "text", "content": content}
    yield {"type": "turn_end", "message": {"role": "assistant", "content": "".join(parts)}}


async def _run_tool_call(
    db: AsyncSession, call: dict[str, Any], tool_activity: list[dict[str, Any]]
) -> tuple[tuple[str, str], dict[str, Any]]:
    """Execute one tool call; return (sse_events, tool message for the model)."""
    from llm.client import parse_tool_arguments

    function = call.get("function") or {}
    name = str(function.get("name") or "")
    call_id = str(call.get("id") or uuid.uuid4())
    arguments, parse_error = parse_tool_arguments(function.get("arguments"))

    activity = ChatToolActivity(
        id=call_id,
        name=name,
        arguments=arguments,
        status="running",
        started_at=datetime.now(UTC).isoformat(),
    )
    started = _sse(ChatStreamEvent(type="tool_call", tool=activity))

    if parse_error:
        result: dict[str, Any] = {"error": parse_error}
    else:
        result = await chat_tool_service.execute_tool(db, name, arguments)

    described = chat_tool_service.summarize_tool_result(name, arguments, result)
    activity = activity.model_copy(
        update={
            "status": "failed" if "error" in result else "completed",
            "summary": described["summary"],
            "href": described["href"],
            "completed_at": datetime.now(UTC).isoformat(),
        }
    )
    tool_activity.append(activity.model_dump())
    finished = _sse(ChatStreamEvent(type="tool_result", tool=activity))

    tool_message = {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(result, default=str),
    }
    return (started, finished), tool_message


def _fallback_tool_summary(tool_activity: list[dict[str, Any]]) -> str:
    lines = [f"- {item.get('name', 'tool')}: {item.get('summary', '')}" for item in tool_activity]
    return "I ran the following tools:\n" + "\n".join(lines)


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
