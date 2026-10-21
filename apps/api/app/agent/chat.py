import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from fastapi.sse import ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.history import load_history
from app.agent.loop import AgentDone, ToolFinished, ToolStarted, run_agent
from app.agent.prompts import build_system_prompt, reply_language
from app.agent.tools import ToolContext
from app.clinic.service import Clinic
from app.core.clock import Clock
from app.core.config import Settings
from app.llm.base import ChatMessage, LLMError, LLMProvider, TextDelta
from app.models import Conversation, Message, PendingAction
from app.rag.embeddings import Embedder, EmbeddingError
from app.rag.retrieve import retrieve
from app.schemas.chat import ConfirmationOut, SourceOut

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Something went wrong. Please try again."


def confirmation_card(clinic: Clinic, action: PendingAction) -> ConfirmationOut:
    return ConfirmationOut.model_validate(
        {
            "action_id": action.id,
            "kind": action.kind,
            "status": clinic.effective_status(action),
            "details": action.details,
            "expires_at": action.expires_at,
            "result": action.result,
        }
    )


async def retrieve_sources(
    *,
    session: AsyncSession,
    embedder: Embedder,
    provider: LLMProvider,
    settings: Settings,
    history: Sequence[ChatMessage],
    user_text: str,
) -> list[SourceOut]:
    try:
        chunks = await retrieve(
            session=session,
            embedder=embedder,
            provider=provider,
            history=history,
            user_text=user_text,
            k=settings.rag_top_k,
            translate=settings.rag_translate_queries,
        )
    except EmbeddingError:
        # Degrade to "no documents": the model is told to say it doesn't know.
        logger.warning("retrieval_failed", exc_info=True)
        return []
    return [
        SourceOut(
            n=n,
            source=c.source,
            title=c.title,
            page=c.page,
            section=c.section,
            lang=c.lang,
            excerpt=c.content,
        )
        for n, c in enumerate(chunks, start=1)
    ]


async def stream_reply(
    *,
    session: AsyncSession,
    provider: LLMProvider,
    embedder: Embedder,
    settings: Settings,
    clock: Clock,
    conversation: Conversation,
    user_text: str,
    ui_language: str,
    action: PendingAction | None = None,
    confirm: bool = False,
) -> AsyncIterator[ServerSentEvent]:
    """Save the user's message, run the agent, stream SSE events, then save the reply.

    Events: `meta` → `action_result`? (a Confirm / Cancel press) → `sources`? → (`delta` |
    `tool` | `confirmation`)* → `done` | `error`.
    """
    clinic = Clinic(session, settings, clock())
    action_result: dict[str, Any] | None = None
    if action is not None:
        outcome = await clinic.decide(action, confirm=confirm)
        action_result = {
            "action_id": str(action.id),
            "kind": action.kind,
            "decision": "confirm" if confirm else "decline",
            **outcome,
        }
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=user_text,
        action_result=action_result,
    )
    session.add(user_message)
    await session.commit()  # the decision and the message are saved together
    yield ServerSentEvent(
        event="meta",
        data={"conversation_id": str(conversation.id), "user_message_id": user_message.id},
    )
    if action_result is not None:
        yield ServerSentEvent(event="action_result", data=action_result)

    ctx = ToolContext(clinic=clinic, conversation_id=conversation.id)
    sources: list[SourceOut] = []
    done: AgentDone | None = None
    try:
        history = await load_history(session, conversation.id, settings.chat_history_limit)
        if action is None:  # a button press is not a question about the documents
            sources = await retrieve_sources(
                session=session,
                embedder=embedder,
                provider=provider,
                settings=settings,
                history=history,
                user_text=user_text,
            )
        if sources:
            yield ServerSentEvent(event="sources", data=[s.model_dump() for s in sources])
        language = reply_language(user_text, ui_language)
        system = build_system_prompt(
            language, sources, now=clinic.local(clinic.now), ui_language=ui_language
        )
        async for event in run_agent(
            provider,
            system=system,
            history=history,
            ctx=ctx,
            max_steps=settings.agent_max_steps,
            max_tokens=settings.llm_max_tokens,
            language=language,
        ):
            match event:
                case TextDelta(text=text):
                    yield ServerSentEvent(event="delta", data={"text": text})
                case ToolStarted(call=call):
                    yield ServerSentEvent(
                        event="tool", data={"id": call.id, "name": call.name, "status": "running"}
                    )
                case ToolFinished(call=call):
                    await session.commit()  # a proposed card must exist before it is shown
                    yield ServerSentEvent(
                        event="tool",
                        data={
                            "id": call.id,
                            "name": call.name,
                            "status": "done" if event.ok else "error",
                        },
                    )
                    if ctx.proposed is not None and event.result.get("status") == (
                        "awaiting_patient_confirmation"
                    ):
                        card = confirmation_card(clinic, ctx.proposed)
                        yield ServerSentEvent(
                            event="confirmation", data=card.model_dump(mode="json")
                        )
                case AgentDone():
                    done = event
        if done is None:
            raise LLMError(GENERIC_ERROR)
    except LLMError as exc:
        logger.warning("llm_error", exc_info=exc)
        yield ServerSentEvent(event="error", data={"message": str(exc)})
        return
    except Exception:
        logger.exception("chat_stream_failed")
        yield ServerSentEvent(event="error", data={"message": GENERIC_ERROR})
        return

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=done.text,
        sources=[s.model_dump() for s in sources] or None,
        tool_calls=done.tool_calls or None,
        action_id=ctx.proposed.id if ctx.proposed is not None else None,
    )
    session.add(assistant_message)
    await session.commit()

    logger.info(
        "chat_turn",
        extra={
            "fields": {
                "conversation_id": str(conversation.id),
                "model": done.model,
                "steps": done.steps,
                "input_tokens": done.input_tokens,
                "output_tokens": done.output_tokens,
                "stop_reason": done.stop_reason,
                "tools": [c["name"] for c in done.tool_calls],
                "sources": [f"{s.source}#{s.page or s.section}" for s in sources],
            }
        },
    )
    yield ServerSentEvent(
        event="done",
        data={
            "message_id": assistant_message.id,
            "model": done.model,
            "usage": {"input_tokens": done.input_tokens, "output_tokens": done.output_tokens},
        },
    )
