from collections.abc import AsyncIterator, Sequence

import anthropic
import httpx2
from anthropic.types import MessageParam

from app.llm.base import ChatMessage, LLMError, StreamEnd, StreamEvent, TextDelta, Usage


class AnthropicProvider:
    def __init__(
        self, *, api_key: str, model: str, http_client: httpx2.AsyncClient | None = None
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key, http_client=http_client)
        self._model = model

    async def stream(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        params: list[MessageParam] = [{"role": m.role, "content": m.content} for m in messages]
        try:
            async with self._client.messages.stream(
                model=self._model, max_tokens=max_tokens, system=system, messages=params
            ) as stream:
                async for text in stream.text_stream:
                    yield TextDelta(text)
                final = await stream.get_final_message()
        except anthropic.APIError as exc:
            raise LLMError("The assistant is temporarily unavailable. Please try again.") from exc

        yield StreamEnd(
            model=final.model,
            usage=Usage(
                input_tokens=final.usage.input_tokens, output_tokens=final.usage.output_tokens
            ),
            stop_reason=final.stop_reason,
        )
