import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.api.v1 import chat as chat_api
from app.schemas.chat import ChatSessionResponse, ChatSessionSummary
from app.services import chat_context_service, chat_service

NOW = datetime(2026, 5, 3, tzinfo=UTC)
VALID_STRATEGY_CODE = """from engine import Signal, Strategy


class GeneratedMomentumStrategy(Strategy):
    def init(self, params: dict) -> None:
        self.lookback = int(params.get("lookback", 20))
        self.closes = []

    def next(self, row: dict, portfolio) -> Signal | None:
        self.closes.append(row["close"])
        if len(self.closes) < self.lookback:
            return None
        average = sum(self.closes[-self.lookback:]) / self.lookback
        if row["close"] > average and row["symbol"] not in portfolio.position_symbols:
            return Signal(symbol=row["symbol"], side="buy", quantity=10)
        return None
"""


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        data = "\n".join(
            line.removeprefix("data: ") for line in block.splitlines() if line.startswith("data: ")
        )
        if data:
            events.append(json.loads(data))
    return events


def fake_session(session_id: uuid.UUID, context: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=session_id,
        context=context or {},
        created_at=NOW,
        updated_at=NOW,
    )


def fake_message(
    session_id: uuid.UUID,
    role: str,
    content: str,
    ordering: int,
    linked_run_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        role=role,
        content=content,
        linked_run_id=linked_run_id,
        metadata_=metadata or {},
        ordering=ordering,
        created_at=NOW,
    )


class FakeLLM:
    async def chat(
        self, messages: list[dict[str, str]], stream: bool = True
    ) -> AsyncGenerator[str]:
        yield "Assistant"
        yield " response"


class CapturingLLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def chat(
        self, messages: list[dict[str, str]], stream: bool = True
    ) -> AsyncGenerator[str]:
        self.messages = messages
        yield "Context response"


class StaticLLM:
    def __init__(self, response: str) -> None:
        self.response = response

    async def chat(
        self, messages: list[dict[str, str]], stream: bool = True
    ) -> AsyncGenerator[str]:
        yield self.response


def patch_chat_storage(
    monkeypatch: pytest.MonkeyPatch,
    session: SimpleNamespace,
    messages: list[SimpleNamespace],
) -> None:
    async def get_or_create_session(_db: object, _data: object) -> SimpleNamespace:
        return session

    async def append_message(
        _db: object,
        current_session_id: uuid.UUID,
        role: str,
        content: str,
        linked_run_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> SimpleNamespace:
        message = fake_message(
            current_session_id,
            role,
            content,
            len(messages) + 1,
            linked_run_id=linked_run_id,
            metadata=metadata,
        )
        messages.append(message)
        return message

    async def get_session_summary(
        _db: object, current_session_id: uuid.UUID
    ) -> ChatSessionSummary:
        return ChatSessionSummary(
            id=current_session_id,
            context=session.context,
            created_at=NOW,
            updated_at=NOW,
            message_count=len(messages),
            last_message_at=messages[-1].created_at if messages else None,
        )

    async def list_messages(_db: object, _session_id: uuid.UUID) -> list[SimpleNamespace]:
        return messages

    monkeypatch.setattr(chat_service, "get_or_create_session", get_or_create_session)
    monkeypatch.setattr(chat_service, "append_message", append_message)
    monkeypatch.setattr(chat_service, "get_session_summary", get_session_summary)
    monkeypatch.setattr(chat_service, "list_messages", list_messages)


@pytest.mark.asyncio
async def test_chat_rejects_empty_messages(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"message": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "Message cannot be empty"


@pytest.mark.asyncio
async def test_chat_returns_404_for_missing_session(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def missing_session(_db: object, _data: object) -> None:
        return None

    monkeypatch.setattr(chat_service, "get_or_create_session", missing_session)

    response = await client.post(
        "/api/v1/chat",
        json={"session_id": str(uuid.uuid4()), "message": "Hello"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat session not found"


@pytest.mark.asyncio
async def test_chat_streams_session_chunks_and_done(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = uuid.uuid4()
    session = fake_session(session_id)
    messages: list[SimpleNamespace] = []

    async def get_or_create_session(_db: object, _data: object) -> SimpleNamespace:
        return session

    async def append_message(
        _db: object,
        current_session_id: uuid.UUID,
        role: str,
        content: str,
        linked_run_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> SimpleNamespace:
        message = fake_message(
            current_session_id,
            role,
            content,
            len(messages) + 1,
            linked_run_id=linked_run_id,
            metadata=metadata,
        )
        messages.append(message)
        return message

    async def get_session_summary(
        _db: object, current_session_id: uuid.UUID
    ) -> ChatSessionSummary:
        return ChatSessionSummary(
            id=current_session_id,
            context={},
            created_at=NOW,
            updated_at=NOW,
            message_count=len(messages),
            last_message_at=messages[-1].created_at if messages else None,
        )

    async def list_messages(_db: object, _session_id: uuid.UUID) -> list[SimpleNamespace]:
        return messages

    monkeypatch.setattr(chat_service, "get_or_create_session", get_or_create_session)
    monkeypatch.setattr(chat_service, "append_message", append_message)
    monkeypatch.setattr(chat_service, "get_session_summary", get_session_summary)
    monkeypatch.setattr(chat_service, "list_messages", list_messages)
    monkeypatch.setattr(chat_api.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(chat_api, "_get_llm_client", lambda: FakeLLM())

    response = await client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert [event["type"] for event in events] == ["session", "chunk", "chunk", "done"]
    assert events[1]["content"] == "Assistant"
    assert events[2]["content"] == " response"
    assert events[3]["message"]["content"] == "Assistant response"
    assert [message.role for message in messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_chat_stores_valid_generated_strategy_metadata(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = fake_session(uuid.uuid4())
    messages: list[SimpleNamespace] = []
    patch_chat_storage(monkeypatch, session, messages)
    monkeypatch.setattr(chat_api.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        chat_api,
        "_get_llm_client",
        lambda: StaticLLM(f"Here is a strategy:\n```python\n{VALID_STRATEGY_CODE}\n```"),
    )

    response = await client.post("/api/v1/chat", json={"message": "Generate a strategy"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    generated = events[-1]["message"]["metadata"]["generated_strategy"]
    assert generated["valid"] is True
    assert generated["class_name"] == "GeneratedMomentumStrategy"
    assert generated["errors"] == []
    assert "class GeneratedMomentumStrategy(Strategy)" in generated["code"]
    assert messages[-1].metadata_["generated_strategy"] == generated


@pytest.mark.asyncio
async def test_chat_stores_invalid_generated_strategy_metadata_without_valid_action(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = fake_session(uuid.uuid4())
    messages: list[SimpleNamespace] = []
    patch_chat_storage(monkeypatch, session, messages)
    monkeypatch.setattr(chat_api.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        chat_api,
        "_get_llm_client",
        lambda: StaticLLM("```python\nclass EmptyStrategy(Strategy):\n    pass\n```"),
    )

    response = await client.post("/api/v1/chat", json={"message": "Generate a strategy"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    generated = events[-1]["message"]["metadata"]["generated_strategy"]
    assert generated["valid"] is False
    assert generated["class_name"] == "EmptyStrategy"
    assert generated["code"] == "class EmptyStrategy(Strategy):\n    pass"
    assert generated["errors"] == [
        "EmptyStrategy must define init().",
        "EmptyStrategy must define next().",
    ]


@pytest.mark.asyncio
async def test_chat_stores_valid_assistant_action_metadata(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = fake_session(uuid.uuid4())
    strategy_id = uuid.uuid4()
    messages: list[SimpleNamespace] = []
    patch_chat_storage(monkeypatch, session, messages)
    monkeypatch.setattr(chat_api.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        chat_api,
        "_get_llm_client",
        lambda: StaticLLM(
            "I can run that after confirmation.\n"
            "```rewind-action\n"
            f'{{"actions": [{{"type": "run_backtest", "payload": '
            f'{{"strategy_id": "{strategy_id}", "params": {{"symbol": "AAPL"}}}}}}]}}\n'
            "```"
        ),
    )

    response = await client.post("/api/v1/chat", json={"message": "Run a backtest"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    actions = events[-1]["message"]["metadata"]["assistant_actions"]
    assert len(actions) == 1
    assert uuid.UUID(actions[0]["id"])
    assert actions[0]["type"] == "run_backtest"
    assert actions[0]["status"] == "proposed"
    assert actions[0]["payload"] == {
        "strategy_id": str(strategy_id),
        "params": {"symbol": "AAPL"},
    }
    assert "created_at" in actions[0]
    assert messages[-1].metadata_["assistant_actions"] == actions


@pytest.mark.asyncio
async def test_chat_stores_create_strategy_and_run_action_metadata(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = fake_session(uuid.uuid4())
    messages: list[SimpleNamespace] = []
    patch_chat_storage(monkeypatch, session, messages)
    monkeypatch.setattr(chat_api.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        chat_api,
        "_get_llm_client",
        lambda: StaticLLM(
            "Here is a testable strategy.\n"
            f"```python\n{VALID_STRATEGY_CODE}\n```\n"
            "```rewind-action\n"
            '{"actions": [{"type": "create_strategy_and_run", "payload": '
            '{"name": "Generated Momentum", "description": "Created from chat.", '
            '"params": {"symbol": "AAPL"}}}]}\n'
            "```"
        ),
    )

    response = await client.post(
        "/api/v1/chat",
        json={"message": "Test a momentum strategy on AAPL"},
    )

    assert response.status_code == 200
    events = parse_sse(response.text)
    actions = events[-1]["message"]["metadata"]["assistant_actions"]
    assert len(actions) == 1
    action = actions[0]
    assert uuid.UUID(action["id"])
    assert action["type"] == "create_strategy_and_run"
    assert action["label"] == "Create strategy and run backtest"
    assert action["status"] == "proposed"
    assert action["payload"] == {
        "name": "Generated Momentum",
        "description": "Created from chat.",
        "code": VALID_STRATEGY_CODE.strip(),
        "params": {"symbol": "AAPL"},
        "class_name": "GeneratedMomentumStrategy",
    }
    assert "created_at" in action
    assert messages[-1].metadata_["assistant_actions"] == actions


@pytest.mark.asyncio
async def test_chat_keeps_invalid_assistant_action_errors_out_of_actions(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = fake_session(uuid.uuid4())
    messages: list[SimpleNamespace] = []
    patch_chat_storage(monkeypatch, session, messages)
    monkeypatch.setattr(chat_api.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        chat_api,
        "_get_llm_client",
        lambda: StaticLLM(
            "```rewind-action\n"
            '{"actions": [{"type": "run_backtest", "payload": {"strategy_id": "bad"}}]}\n'
            "```"
        ),
    )

    response = await client.post("/api/v1/chat", json={"message": "Run a backtest"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    metadata = events[-1]["message"]["metadata"]
    assert "assistant_actions" not in metadata
    assert metadata["assistant_action_errors"] == [
        "Action block 1, action 1 payload.strategy_id must be a valid UUID."
    ]


@pytest.mark.asyncio
async def test_chat_action_audit_endpoint_records_result(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = uuid.uuid4()
    message_id = uuid.uuid4()
    action_id = uuid.uuid4()

    async def record_assistant_action(
        _db: object,
        current_message_id: uuid.UUID,
        current_action_id: uuid.UUID,
        status: str,
        result: dict | None = None,
        error: str = "",
    ) -> SimpleNamespace:
        assert current_message_id == message_id
        assert current_action_id == action_id
        assert status == "completed"
        assert result == {"run_id": "run-1"}
        assert error == ""
        return fake_message(
            session_id,
            "assistant",
            "Run it",
            2,
            metadata={
                "assistant_actions": [
                    {
                        "id": str(action_id),
                        "type": "run_backtest",
                        "label": "Run backtest",
                        "status": "completed",
                        "payload": {},
                        "result": {"run_id": "run-1"},
                    }
                ]
            },
        )

    monkeypatch.setattr(chat_service, "record_assistant_action", record_assistant_action)

    response = await client.post(
        f"/api/v1/chat/messages/{message_id}/actions/{action_id}",
        json={"status": "completed", "result": {"run_id": "run-1"}},
    )

    assert response.status_code == 200
    action = response.json()["metadata"]["assistant_actions"][0]
    assert action["status"] == "completed"
    assert action["result"] == {"run_id": "run-1"}


@pytest.mark.asyncio
async def test_chat_rejects_invalid_context_before_writing_message(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def append_message(*_args: object, **_kwargs: object) -> SimpleNamespace:
        pytest.fail("append_message should not be called for invalid context")

    monkeypatch.setattr(chat_service, "append_message", append_message)

    response = await client.post(
        "/api/v1/chat",
        json={"message": "Hello", "context": {"type": "run"}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "context.run_id must be a UUID string"


@pytest.mark.asyncio
async def test_chat_returns_404_for_missing_context_run_before_writing_message(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = uuid.uuid4()

    async def build_prompt_context(_db: object, _context: dict) -> dict:
        raise chat_context_service.ChatContextNotFoundError("Run not found")

    async def append_message(*_args: object, **_kwargs: object) -> SimpleNamespace:
        pytest.fail("append_message should not be called when context data is missing")

    monkeypatch.setattr(chat_context_service, "build_prompt_context", build_prompt_context)
    monkeypatch.setattr(chat_service, "append_message", append_message)

    response = await client.post(
        "/api/v1/chat",
        json={"message": "Hello", "context": {"type": "run", "run_id": str(run_id)}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Run not found"


@pytest.mark.asyncio
async def test_chat_injects_run_context_and_links_messages(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()
    session = fake_session(session_id, {"type": "run", "run_id": str(run_id)})
    messages: list[SimpleNamespace] = []
    llm = CapturingLLM()

    async def build_prompt_context(_db: object, context: dict) -> dict:
        assert context == {"type": "run", "run_id": str(run_id)}
        return {
            "context_type": "run",
            "run": {"id": str(run_id), "metrics": {"total_return": -0.12}},
            "strategy": {"code": "class LosingStrategy: pass"},
            "limitations": ["Only provided context may be used."],
        }

    async def get_or_create_session(_db: object, data: object) -> SimpleNamespace:
        assert data.context == {"type": "run", "run_id": str(run_id)}
        return session

    async def append_message(
        _db: object,
        current_session_id: uuid.UUID,
        role: str,
        content: str,
        linked_run_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> SimpleNamespace:
        message = fake_message(
            current_session_id,
            role,
            content,
            len(messages) + 1,
            linked_run_id=linked_run_id,
            metadata=metadata,
        )
        messages.append(message)
        return message

    async def get_session_summary(
        _db: object, current_session_id: uuid.UUID
    ) -> ChatSessionSummary:
        return ChatSessionSummary(
            id=current_session_id,
            context=session.context,
            created_at=NOW,
            updated_at=NOW,
            message_count=len(messages),
            last_message_at=messages[-1].created_at if messages else None,
        )

    async def list_messages(_db: object, _session_id: uuid.UUID) -> list[SimpleNamespace]:
        return messages

    monkeypatch.setattr(chat_context_service, "build_prompt_context", build_prompt_context)
    monkeypatch.setattr(chat_service, "get_or_create_session", get_or_create_session)
    monkeypatch.setattr(chat_service, "append_message", append_message)
    monkeypatch.setattr(chat_service, "get_session_summary", get_session_summary)
    monkeypatch.setattr(chat_service, "list_messages", list_messages)
    monkeypatch.setattr(chat_api.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(chat_api, "_get_llm_client", lambda: llm)

    response = await client.post(
        "/api/v1/chat",
        json={"message": "Why did it lose?", "context": {"type": "run", "run_id": str(run_id)}},
    )

    assert response.status_code == 200
    assert '"total_return": -0.12' in llm.messages[0]["content"]
    assert "class LosingStrategy: pass" in llm.messages[0]["content"]
    assert [message.linked_run_id for message in messages] == [run_id, run_id]
    assert [message.metadata_ for message in messages] == [{}, {}]


@pytest.mark.asyncio
async def test_chat_missing_provider_key_streams_error_without_assistant_message(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = uuid.uuid4()
    session = fake_session(session_id)
    messages: list[SimpleNamespace] = []

    async def get_or_create_session(_db: object, _data: object) -> SimpleNamespace:
        return session

    async def append_message(
        _db: object,
        current_session_id: uuid.UUID,
        role: str,
        content: str,
        linked_run_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> SimpleNamespace:
        message = fake_message(
            current_session_id,
            role,
            content,
            len(messages) + 1,
            linked_run_id=linked_run_id,
            metadata=metadata,
        )
        messages.append(message)
        return message

    async def get_session_summary(
        _db: object, current_session_id: uuid.UUID
    ) -> ChatSessionSummary:
        return ChatSessionSummary(
            id=current_session_id,
            context={},
            created_at=NOW,
            updated_at=NOW,
            message_count=len(messages),
            last_message_at=messages[-1].created_at if messages else None,
        )

    async def list_messages(_db: object, _session_id: uuid.UUID) -> list[SimpleNamespace]:
        return messages

    monkeypatch.setattr(chat_service, "get_or_create_session", get_or_create_session)
    monkeypatch.setattr(chat_service, "append_message", append_message)
    monkeypatch.setattr(chat_service, "get_session_summary", get_session_summary)
    monkeypatch.setattr(chat_service, "list_messages", list_messages)
    monkeypatch.setattr(chat_api.settings, "openai_api_key", "")

    response = await client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert [event["type"] for event in events] == ["session", "error"]
    assert "Assistant failed to respond" in events[1]["error"]
    assert [message.role for message in messages] == ["user"]


@pytest.mark.asyncio
async def test_session_routes_return_expected_shapes(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = uuid.uuid4()
    summary = ChatSessionSummary(
        id=session_id,
        context={},
        created_at=NOW,
        updated_at=NOW,
        message_count=1,
        last_message_at=NOW,
    )
    detail = ChatSessionResponse(
        **summary.model_dump(),
        messages=[
            {
                "id": uuid.uuid4(),
                "session_id": session_id,
                "role": "user",
                "content": "Hello",
                "metadata": {},
                "ordering": 1,
                "created_at": NOW,
            }
        ],
    )

    async def list_sessions(
        _db: object, limit: int = 20, offset: int = 0
    ) -> tuple[list[ChatSessionSummary], int]:
        return [summary], 1

    async def get_session_detail(
        _db: object, current_session_id: uuid.UUID
    ) -> ChatSessionResponse | None:
        return detail if current_session_id == session_id else None

    async def delete_session(_db: object, current_session_id: uuid.UUID) -> bool:
        return current_session_id == session_id

    monkeypatch.setattr(chat_service, "list_sessions", list_sessions)
    monkeypatch.setattr(chat_service, "get_session_detail", get_session_detail)
    monkeypatch.setattr(chat_service, "delete_session", delete_session)

    list_response = await client.get("/api/v1/chat/sessions")
    detail_response = await client.get(f"/api/v1/chat/sessions/{session_id}")
    delete_response = await client.delete(f"/api/v1/chat/sessions/{session_id}")

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["id"] == str(session_id)
    assert detail_response.status_code == 200
    assert detail_response.json()["messages"][0]["content"] == "Hello"
    assert delete_response.status_code == 204
