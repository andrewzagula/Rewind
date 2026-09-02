from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI


def accumulate_tool_call_delta(
    store: dict[int, dict[str, Any]],
    index: int,
    call_id: str | None,
    name: str | None,
    arguments: str | None,
) -> None:
    """Merge one streamed tool-call fragment into ``store`` keyed by the call index."""
    entry = store.setdefault(index, {"id": "", "name": "", "arguments": ""})
    if call_id:
        entry["id"] = call_id
    if name:
        entry["name"] += name
    if arguments:
        entry["arguments"] += arguments


def build_assistant_message(content: str, store: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Shape accumulated stream state as an OpenAI assistant message."""
    message: dict[str, Any] = {"role": "assistant", "content": content or None}
    tool_calls = [
        {
            "id": entry["id"] or f"call_{index}",
            "type": "function",
            "function": {"name": entry["name"], "arguments": entry["arguments"] or "{}"},
        }
        for index, entry in sorted(store.items())
        if entry["name"]
    ]
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def parse_tool_arguments(raw: str | None) -> tuple[dict[str, Any], str]:
    """Decode tool-call arguments; return (arguments, error) with error empty on success."""
    if not raw or not raw.strip():
        return {}, ""
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"Tool arguments were not valid JSON: {exc.msg}"
    if not isinstance(decoded, dict):
        return {}, "Tool arguments must be a JSON object."
    return decoded, ""


class LLMClient:
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        stream: bool = True,
    ) -> AsyncGenerator[str]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=stream,
        )

        if stream:
            async for chunk in response:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        else:
            yield response.choices[0].message.content or ""

    async def stream_turn(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any]]:
        """Stream one assistant turn.

        Yields ``{"type": "text", "content": str}`` for each text fragment and finishes with
        ``{"type": "turn_end", "message": <assistant message>}`` where the message carries any
        ``tool_calls`` the model requested.
        """
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        content_parts: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                yield {"type": "text", "content": delta.content}
            for call in delta.tool_calls or []:
                function = call.function
                accumulate_tool_call_delta(
                    tool_calls,
                    call.index,
                    call.id,
                    function.name if function else None,
                    function.arguments if function else None,
                )

        yield {
            "type": "turn_end",
            "message": build_assistant_message("".join(content_parts), tool_calls),
        }
