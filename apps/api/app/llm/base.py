from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


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


StreamEvent = TextDelta | StreamEnd


class LLMError(Exception):
    """Provider failure. The message is safe to show to end users."""


class LLMProvider(Protocol):
    """Streams one assistant reply: zero or more TextDelta events, then exactly one StreamEnd."""

    def stream(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int
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
