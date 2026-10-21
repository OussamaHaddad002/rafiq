"""Shared test doubles for the agent: a scripted LLM and a pinned clock."""

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from itertools import count

from app.llm.base import ChatMessage, StreamEnd, StreamEvent, TextDelta, ToolCall, ToolSpec, Usage
from app.rag.query import QUERY_PROMPT

# Wednesday 21 October 2026, 09:00 in Tunis (UTC+1, no daylight saving time).
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)

Step = str | list[tuple[str, dict[str, object]]]  # a text reply, or tool calls (name, args)


class ScriptedProvider:
    """Plays back a script, one step per model call: text, or a list of tool calls.

    Records what the model was given, so tests can assert on prompts and tool results.
    """

    def __init__(self, *steps: Step) -> None:
        self.steps = list(steps)
        self.calls: list[tuple[str, list[ChatMessage], list[str]]] = []
        self.translations = 0
        self._ids = count(1)

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        max_tokens: int,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[StreamEvent]:
        if system == QUERY_PROMPT:
            # Query translation runs before the agent; answer it without using up a step.
            self.translations += 1
            yield TextDelta("{}")
            yield StreamEnd(model="scripted", usage=Usage(50, 5), stop_reason="end_turn")
            return
        self.calls.append((system, list(messages), [t.name for t in tools]))
        step = self.steps.pop(0) if self.steps else "OK."
        if isinstance(step, str):
            yield TextDelta(step)
            yield StreamEnd(model="scripted", usage=Usage(100, 10), stop_reason="end_turn")
            return
        calls = tuple(ToolCall(f"call_{next(self._ids)}", name, dict(args)) for name, args in step)
        yield StreamEnd(
            model="scripted", usage=Usage(100, 10), stop_reason="tool_calls", tool_calls=calls
        )

    def tool_results(self) -> list[ChatMessage]:
        """Tool results the model saw on its last call."""
        return [m for m in self.calls[-1][1] if m.role == "tool"]
