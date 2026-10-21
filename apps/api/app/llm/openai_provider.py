from collections.abc import AsyncIterator, Sequence

import httpx2
import openai
from openai import omit
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseIncompleteEvent,
    ResponseInputParam,
    ResponseTextDeltaEvent,
)
from openai.types.shared import ReasoningEffort

from app.llm.base import ChatMessage, LLMError, StreamEnd, StreamEvent, TextDelta, Usage

UNAVAILABLE = "The assistant is temporarily unavailable. Please try again."
_REASONING_MODEL_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def supports_reasoning(model: str) -> bool:
    return model.startswith(_REASONING_MODEL_PREFIXES)


class OpenAIProvider:
    """OpenAI Responses API. Responses are not stored on OpenAI's side (`store=False`)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: ReasoningEffort = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key, http_client=http_client)
        self._model = model
        # Non-reasoning models (e.g. gpt-4o-mini) reject the parameter, so drop it for them.
        self._reasoning_effort = reasoning_effort if supports_reasoning(model) else None

    async def stream(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        conversation: ResponseInputParam = [
            {"role": m.role, "content": m.content} for m in messages
        ]

        final: Response | None = None
        try:
            stream = await self._client.responses.create(
                model=self._model,
                instructions=system,
                input=conversation,
                max_output_tokens=max_tokens,
                # Reasoning tokens are billed as output: keep effort low for a receptionist.
                reasoning={"effort": self._reasoning_effort} if self._reasoning_effort else omit,
                store=False,
                stream=True,
            )
            async for event in stream:
                match event:
                    case ResponseTextDeltaEvent():
                        yield TextDelta(event.delta)
                    case ResponseCompletedEvent() | ResponseIncompleteEvent():
                        final = event.response
                    case ResponseFailedEvent() | ResponseErrorEvent():
                        raise LLMError(UNAVAILABLE)
        except openai.OpenAIError as exc:
            raise LLMError(UNAVAILABLE) from exc

        if final is None:
            raise LLMError(UNAVAILABLE)
        usage = final.usage
        yield StreamEnd(
            model=final.model,
            usage=Usage(
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
            ),
            stop_reason=(
                final.incomplete_details.reason if final.incomplete_details else final.status
            ),
        )
