import logging
import uuid
from collections.abc import AsyncIterator, Sequence

from fastapi.sse import ServerSentEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import build_system_prompt, reply_language
from app.core.config import Settings
from app.llm.base import ChatMessage, LLMError, LLMProvider, StreamEnd, TextDelta
from app.models import Conversation, Message
from app.rag.embeddings import Embedder, EmbeddingError
from app.rag.retrieve import retrieve
from app.schemas.chat import SourceOut

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Something went wrong. Please try again."


def normalize_history(messages: Sequence[ChatMessage]) -> list[ChatMessage]:
    """Make stored history valid model input.

    The history must start with a user turn (truncation can cut it mid-exchange), and
    consecutive turns from the same role are merged (a failed or interrupted reply leaves
    two user messages in a row).
    """
    normalized: list[ChatMessage] = []
    for message in messages:
        if not normalized and message.role != "user":
            continue
        if normalized and normalized[-1].role == message.role:
            previous = normalized.pop()
            message = ChatMessage(message.role, f"{previous.content}\n\n{message.content}")
        normalized.append(message)
    return normalized


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


async def load_history(
    session: AsyncSession, conversation_id: uuid.UUID, limit: int
) -> list[ChatMessage]:
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    history = [
        ChatMessage("user" if m.role == "user" else "assistant", m.content)
        for m in reversed(rows.all())
    ]
    return normalize_history(history)


async def stream_reply(
    *,
    session: AsyncSession,
    provider: LLMProvider,
    embedder: Embedder,
    settings: Settings,
    conversation: Conversation,
    user_text: str,
    ui_language: str,
) -> AsyncIterator[ServerSentEvent]:
    """Save the user's message, stream the assistant's reply as SSE events, then save it.

    Events: `meta` (ids) → `sources`? (cited excerpts) → `delta`* (text chunks)
    → `done` (message id, usage) | `error`.
    """
    user_message = Message(conversation_id=conversation.id, role="user", content=user_text)
    session.add(user_message)
    await session.commit()
    yield ServerSentEvent(
        event="meta",
        data={"conversation_id": str(conversation.id), "user_message_id": user_message.id},
    )

    parts: list[str] = []
    end: StreamEnd | None = None
    try:
        history = await load_history(session, conversation.id, settings.chat_history_limit)
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
        async for event in provider.stream(
            system=build_system_prompt(reply_language(user_text, ui_language), sources),
            messages=history,
            max_tokens=settings.llm_max_tokens,
        ):
            match event:
                case TextDelta(text=text):
                    parts.append(text)
                    yield ServerSentEvent(event="delta", data={"text": text})
                case StreamEnd():
                    end = event
        if end is None:
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
        content="".join(parts),
        sources=[s.model_dump() for s in sources] or None,
    )
    session.add(assistant_message)
    await session.commit()

    logger.info(
        "chat_turn",
        extra={
            "fields": {
                "conversation_id": str(conversation.id),
                "model": end.model,
                "input_tokens": end.usage.input_tokens,
                "output_tokens": end.usage.output_tokens,
                "stop_reason": end.stop_reason,
                "sources": [f"{s.source}#{s.page or s.section}" for s in sources],
            }
        },
    )
    yield ServerSentEvent(
        event="done",
        data={
            "message_id": assistant_message.id,
            "model": end.model,
            "usage": {
                "input_tokens": end.usage.input_tokens,
                "output_tokens": end.usage.output_tokens,
            },
        },
    )
