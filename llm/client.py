from __future__ import annotations

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI


class LLMClient:
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def chat(
        self,
        messages: list[dict[str, str]],
        stream: bool = True,
    ) -> AsyncGenerator[str]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=stream,
        )

        if stream:
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        else:
            yield response.choices[0].message.content or ""
