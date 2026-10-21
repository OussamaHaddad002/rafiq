from collections.abc import AsyncIterator, Sequence
from typing import Literal

import anthropic
import httpx2
from anthropic import omit
from anthropic.types import ContentBlockParam, MessageParam, ToolParam, ToolUseBlock

from app.llm.base import (
    ChatMessage,
    LLMError,
    StreamEnd,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)


def to_messages(messages: Sequence[ChatMessage]) -> list[MessageParam]:
    """Provider-neutral messages -> Anthropic messages.

    Tool results travel in a user turn, and consecutive turns of the same role are merged
    (e.g. tool results followed by the patient's next message).
    """
    turns: list[tuple[Literal["user", "assistant"], list[ContentBlockParam]]] = []
    for message in messages:
        role: Literal["user", "assistant"]
        blocks: list[ContentBlockParam] = []
        if message.role == "tool":
            role = "user"
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id or "",
                    "content": message.content,
                }
            )
        else:
            role = message.role
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            for call in message.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                )
        if turns and turns[-1][0] == role:
            turns[-1][1].extend(blocks)
        else:
            turns.append((role, blocks))
    return [{"role": role, "content": blocks} for role, blocks in turns]


def to_tools(tools: Sequence[ToolSpec]) -> list[ToolParam]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": {"type": "object", **tool.parameters},
        }
        for tool in tools
    ]


class AnthropicProvider:
    def __init__(
        self, *, api_key: str, model: str, http_client: httpx2.AsyncClient | None = None
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key, http_client=http_client)
        self._model = model

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        max_tokens: int,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[StreamEvent]:
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=to_messages(messages),
                tools=to_tools(tools) if tools else omit,
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
            tool_calls=tuple(
                ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
                for block in final.content
                if isinstance(block, ToolUseBlock)
            ),
        )
