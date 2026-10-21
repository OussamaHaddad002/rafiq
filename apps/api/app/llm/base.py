from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of the arguments


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One provider-neutral conversation item.

    - user / assistant: `content` text; an assistant item may also carry `tool_calls`
    - tool: the JSON result of the call `tool_call_id`, in `content`
    """

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class StreamEnd:
    model: str
    usage: Usage
    stop_reason: str | None
    tool_calls: tuple[ToolCall, ...] = ()


StreamEvent = TextDelta | StreamEnd


class LLMError(Exception):
    """Provider failure. The message is safe to show to end users."""


class LLMProvider(Protocol):
    """Streams one assistant reply: zero or more TextDelta events, then exactly one StreamEnd.

    When `tools` are given, the model may answer with tool calls (in `StreamEnd.tool_calls`)
    instead of, or after, text.
    """

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        max_tokens: int,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[StreamEvent]: ...


async def complete(
    provider: LLMProvider, *, system: str, messages: Sequence[ChatMessage], max_tokens: int
) -> tuple[str, StreamEnd | None]:
    """Non-streaming convenience: the full reply text and its usage."""
    parts: list[str] = []
    end: StreamEnd | None = None
    async for event in provider.stream(system=system, messages=messages, max_tokens=max_tokens):
        if isinstance(event, TextDelta):
            parts.append(event.text)
        else:
            end = event
    return "".join(parts), end
