import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy import select

from app.agent.chat import stream_reply
from app.core.config import Settings, get_settings
from app.core.db import SessionDep
from app.llm import ProviderDep
from app.models import Conversation, Message
from app.rag.embeddings import EmbedderDep
from app.schemas.chat import ChatRequest, ConversationOut, MessageOut

router = APIRouter(tags=["chat"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_or_create_conversation(body: ChatRequest, session: SessionDep) -> Conversation:
    # Runs as a dependency so a bad conversation_id is a 404 before the SSE stream starts.
    if body.conversation_id is None:
        conversation = Conversation(language=body.language)
        session.add(conversation)
        await session.flush()
        return conversation
    existing = await session.get(Conversation, body.conversation_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return existing


@router.post("/chat", response_class=EventSourceResponse)
async def chat(
    body: ChatRequest,
    session: SessionDep,
    provider: ProviderDep,
    embedder: EmbedderDep,
    settings: SettingsDep,
    conversation: Annotated[Conversation, Depends(get_or_create_conversation)],
) -> AsyncIterator[ServerSentEvent]:
    async for event in stream_reply(
        session=session,
        provider=provider,
        embedder=embedder,
        settings=settings,
        conversation=conversation,
        user_text=body.message,
        ui_language=body.language,
    ):
        yield event


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: uuid.UUID, session: SessionDep) -> ConversationOut:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    messages = await session.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    )
    return ConversationOut.model_validate(
        {
            "id": conversation.id,
            "language": conversation.language,
            "created_at": conversation.created_at,
            "messages": [MessageOut.model_validate(m) for m in messages],
        }
    )
