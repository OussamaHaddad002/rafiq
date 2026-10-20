from collections.abc import AsyncIterator, Sequence

from app.llm.base import ChatMessage, StreamEnd, StreamEvent, TextDelta, Usage


class FakeProvider:
    """Deterministic echo provider for tests, CI and running without an API key."""

    model = "fake-echo"

    async def stream(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        reply = f"Echo ({len(messages)} messages in context): {messages[-1].content}"
        for start in range(0, len(reply), 8):
            yield TextDelta(reply[start : start + 8])
        yield StreamEnd(
            model=self.model,
            usage=Usage(
                input_tokens=sum(len(m.content) for m in messages) // 4,
                output_tokens=len(reply) // 4,
            ),
            stop_reason="end_turn",
        )
