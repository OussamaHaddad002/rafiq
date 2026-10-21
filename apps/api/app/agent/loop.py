"""The tool loop: model -> tool calls -> results -> model, until it answers in text."""

import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.agent.tools import TOOL_SPECS, ToolContext, run_tool
from app.llm.base import ChatMessage, LLMError, LLMProvider, StreamEnd, TextDelta, ToolCall

logger = logging.getLogger(__name__)

MAX_STEPS_REPLIES = {
    "en": "Sorry, I couldn't finish that request. Please try again, or call the clinic at "
    "+216 70 000 100.",
    "fr": "Désolé, je n'ai pas pu terminer cette demande. Veuillez réessayer ou appeler la "
    "clinique au +216 70 000 100.",
    "ar": "عذرًا، لم أتمكن من إتمام هذا الطلب. يرجى المحاولة مرة أخرى أو الاتصال بالعيادة على "
    "الرقم ‎+216 70 000 100.",
}


@dataclass(frozen=True, slots=True)
class ToolStarted:
    call: ToolCall


@dataclass(frozen=True, slots=True)
class ToolFinished:
    call: ToolCall
    result: dict[str, Any]

    @property
    def ok(self) -> bool:
        return "error" not in self.result


@dataclass(slots=True)
class AgentDone:
    text: str
    model: str = ""
    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


AgentEvent = TextDelta | ToolStarted | ToolFinished | AgentDone


async def run_agent(
    provider: LLMProvider,
    *,
    system: str,
    history: Sequence[ChatMessage],
    ctx: ToolContext,
    max_steps: int,
    max_tokens: int,
    language: str = "en",
) -> AsyncIterator[AgentEvent]:
    """Stream text as it comes and run tools between model calls. Ends with AgentDone.

    `language` is the reply language, used for the fallback when the step limit is hit.
    """
    messages = list(history)
    texts: list[str] = []
    done = AgentDone(text="")
    for step in range(1, max_steps + 1):
        step_text: list[str] = []
        end: StreamEnd | None = None
        async for event in provider.stream(
            system=system, messages=messages, max_tokens=max_tokens, tools=TOOL_SPECS
        ):
            if isinstance(event, TextDelta):
                if not step_text and texts:
                    yield TextDelta("\n\n")  # keep what streams equal to what is saved
                step_text.append(event.text)
                yield event
            else:
                end = event
        if end is None:
            raise LLMError("The assistant is temporarily unavailable. Please try again.")

        done.steps = step
        done.model = end.model
        done.input_tokens += end.usage.input_tokens
        done.output_tokens += end.usage.output_tokens
        done.stop_reason = end.stop_reason
        if text := "".join(step_text):
            texts.append(text)
        if not end.tool_calls:
            break

        messages.append(ChatMessage("assistant", text, tool_calls=end.tool_calls))
        for call in end.tool_calls:
            yield ToolStarted(call)
            started = time.perf_counter()
            result = await run_tool(ctx, call)
            logger.info(
                "tool_call",
                extra={
                    "fields": {
                        "tool": call.name,
                        "ok": "error" not in result,
                        "error": result.get("error"),
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
            done.tool_calls.append(
                {"id": call.id, "name": call.name, "arguments": call.arguments, "result": result}
            )
            yield ToolFinished(call, result)
            messages.append(
                ChatMessage("tool", json.dumps(result, ensure_ascii=False), tool_call_id=call.id)
            )
    else:
        # Still calling tools after the last allowed step: stop instead of looping forever.
        done.stop_reason = "max_steps"
        reply = MAX_STEPS_REPLIES.get(language, MAX_STEPS_REPLIES["en"])
        yield TextDelta(("\n\n" if texts else "") + reply)
        texts.append(reply)

    done.text = "\n\n".join(texts)
    yield done
