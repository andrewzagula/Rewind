import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.v1 import chat as chat_api
from app.schemas.chat import ChatSessionSummary
from app.services import chat_service, chat_tool_service

NOW = datetime(2026, 9, 2, tzinfo=UTC)


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        data = "\n".join(
            line.removeprefix("data: ") for line in block.splitlines() if line.startswith("data: ")
        )
        if data:
            events.append(json.loads(data))
    return events


def fake_message(session_id, role, content, ordering, linked_run_id=None, metadata=None):
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


def patch_storage(
    monkeypatch: pytest.MonkeyPatch, messages: list[SimpleNamespace]
) -> SimpleNamespace:
    session = SimpleNamespace(id=uuid.uuid4(), context={}, created_at=NOW, updated_at=NOW)

    async def get_or_create_session(_db, _data):
        return session

    async def append_message(_db, session_id, role, content, linked_run_id=None, metadata=None):
        message = fake_message(
            session_id, role, content, len(messages) + 1, linked_run_id, metadata
        )
        messages.append(message)
        return message

    async def get_session_summary(_db, session_id):
        return ChatSessionSummary(
            id=session_id,
            context={},
            created_at=NOW,
            updated_at=NOW,
            message_count=len(messages),
            last_message_at=None,
        )

    async def list_messages(_db, _session_id):
        return list(messages)

    monkeypatch.setattr(chat_service, "get_or_create_session", get_or_create_session)
    monkeypatch.setattr(chat_service, "append_message", append_message)
    monkeypatch.setattr(chat_service, "get_session_summary", get_session_summary)
    monkeypatch.setattr(chat_service, "list_messages", list_messages)
    monkeypatch.setattr(chat_api.settings, "openai_api_key", "test-key")
    return session


class ScriptedToolLLM:
    """Replays scripted turns; records the messages and tools it was given."""

    def __init__(self, turns: list[dict[str, Any]]) -> None:
        self.turns = list(turns)
        self.calls: list[tuple[list[dict[str, Any]], list[dict[str, Any]] | None]] = []

    async def stream_turn(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[dict[str, Any]]:
        self.calls.append(([dict(m) for m in messages], tools))
        turn = self.turns.pop(0) if self.turns else {"text": ["(no more turns)"]}
        text_parts = turn.get("text", [])
        for part in text_parts:
            yield {"type": "text", "content": part}
        message: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts) or None}
        if turn.get("tool_calls"):
            message["tool_calls"] = turn["tool_calls"]
        yield {"type": "turn_end", "message": message}


def tool_call(call_id: str, name: str, arguments: Any) -> dict[str, Any]:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw}}


@pytest.mark.asyncio
async def test_chat_runs_tools_and_streams_activity(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[SimpleNamespace] = []
    patch_storage(monkeypatch, messages)
    strategy_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    llm = ScriptedToolLLM(
        [
            {
                "text": ["Running it now."],
                "tool_calls": [tool_call("call_1", "run_backtest", {"strategy_id": strategy_id})],
            },
            {"text": ["The run returned ", "12%."]},
        ]
    )
    monkeypatch.setattr(chat_api, "_get_llm_client", lambda: llm)

    executed: list[tuple[str, dict]] = []

    async def execute_tool(_db, name, arguments):
        executed.append((name, arguments))
        return {
            "run": {
                "id": run_id,
                "status": "completed",
                "metrics": {"total_return": 0.12, "sharpe_ratio": 1.5},
            }
        }

    monkeypatch.setattr(chat_tool_service, "execute_tool", execute_tool)

    response = await client.post("/api/v1/chat", json={"message": "Backtest my strategy"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    types = [event["type"] for event in events]
    assert types[0] == "session"
    assert "tool_call" in types and "tool_result" in types
    assert types[-1] == "done"
    assert types.index("tool_call") < types.index("tool_result")

    started = next(e for e in events if e["type"] == "tool_call")["tool"]
    assert started["name"] == "run_backtest"
    assert started["status"] == "running"
    assert started["arguments"] == {"strategy_id": strategy_id}

    finished = next(e for e in events if e["type"] == "tool_result")["tool"]
    assert finished["status"] == "completed"
    assert "12.00%" in finished["summary"]
    assert finished["href"] == f"/runs/{run_id}"

    assert executed == [("run_backtest", {"strategy_id": strategy_id})]

    done = events[-1]["message"]
    assert done["content"] == "Running it now.\n\nThe run returned 12%."
    assert len(done["metadata"]["tool_activity"]) == 1
    assert done["metadata"]["tool_activity"][0]["name"] == "run_backtest"

    # The model received the tool definitions, then the tool result on the second turn.
    assert llm.calls[0][1] == chat_tool_service.TOOL_DEFINITIONS
    second_turn_messages = llm.calls[1][0]
    assert second_turn_messages[-2]["role"] == "assistant"
    assert second_turn_messages[-2]["tool_calls"][0]["id"] == "call_1"
    assert second_turn_messages[-1]["role"] == "tool"
    assert second_turn_messages[-1]["tool_call_id"] == "call_1"
    assert json.loads(second_turn_messages[-1]["content"])["run"]["id"] == run_id


@pytest.mark.asyncio
async def test_chat_reports_invalid_tool_arguments_to_model(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[SimpleNamespace] = []
    patch_storage(monkeypatch, messages)
    llm = ScriptedToolLLM(
        [
            {"tool_calls": [tool_call("call_x", "get_run", "{not json")]},
            {"text": ["I could not parse that request."]},
        ]
    )
    monkeypatch.setattr(chat_api, "_get_llm_client", lambda: llm)

    async def execute_tool(_db, name, arguments):
        raise AssertionError("execute_tool must not run with unparseable arguments")

    monkeypatch.setattr(chat_tool_service, "execute_tool", execute_tool)

    response = await client.post("/api/v1/chat", json={"message": "Show run"})

    events = parse_sse(response.text)
    finished = next(e for e in events if e["type"] == "tool_result")["tool"]
    assert finished["status"] == "failed"
    assert "not valid JSON" in finished["summary"]
    tool_message = llm.calls[1][0][-1]
    assert tool_message["role"] == "tool"
    assert "not valid JSON" in json.loads(tool_message["content"])["error"]
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_chat_stops_after_max_tool_rounds(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[SimpleNamespace] = []
    patch_storage(monkeypatch, messages)
    endless = [
        {"tool_calls": [tool_call(f"call_{i}", "list_runs", {})]}
        for i in range(chat_tool_service.MAX_TOOL_ROUNDS + 5)
    ]
    llm = ScriptedToolLLM(endless)
    monkeypatch.setattr(chat_api, "_get_llm_client", lambda: llm)

    count = {"n": 0}

    async def execute_tool(_db, name, arguments):
        count["n"] += 1
        return {"total": 0, "items": []}

    monkeypatch.setattr(chat_tool_service, "execute_tool", execute_tool)

    response = await client.post("/api/v1/chat", json={"message": "Loop forever"})

    events = parse_sse(response.text)
    assert count["n"] == chat_tool_service.MAX_TOOL_ROUNDS
    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["content"].startswith("I ran the following tools:")


@pytest.mark.asyncio
async def test_chat_tool_error_is_streamed_as_failed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[SimpleNamespace] = []
    patch_storage(monkeypatch, messages)
    llm = ScriptedToolLLM(
        [
            {
                "tool_calls": [
                    tool_call("call_1", "get_strategy", {"strategy_id": str(uuid.uuid4())})
                ]
            },
            {"text": ["That strategy does not exist."]},
        ]
    )
    monkeypatch.setattr(chat_api, "_get_llm_client", lambda: llm)

    async def execute_tool(_db, name, arguments):
        return {"error": "Strategy not found"}

    monkeypatch.setattr(chat_tool_service, "execute_tool", execute_tool)

    response = await client.post("/api/v1/chat", json={"message": "Show it"})

    events = parse_sse(response.text)
    finished = next(e for e in events if e["type"] == "tool_result")["tool"]
    assert finished["status"] == "failed"
    assert finished["summary"] == "Strategy not found"
    assert events[-1]["message"]["metadata"]["tool_activity"][0]["status"] == "failed"


def test_history_includes_tool_activity_note() -> None:
    metadata = {
        "tool_activity": [
            {
                "name": "run_backtest",
                "arguments": {"strategy_id": "abc"},
                "summary": "Run 1234 completed.",
            }
        ]
    }
    content = chat_api._with_tool_activity_note("Done.", metadata)
    assert content.startswith("Done.")
    assert "[Tool activity in this turn]" in content
    assert 'run_backtest({"strategy_id": "abc"}) -> Run 1234 completed.' in content
    assert chat_api._with_tool_activity_note("Plain", {}) == "Plain"
