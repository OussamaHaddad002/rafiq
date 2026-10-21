import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy import select

from app.agent.chat import confirmation_card, stream_reply
from app.clinic.service import Clinic
from app.core.clock import ClockDep
from app.core.config import Settings, get_settings
from app.core.db import SessionDep
from app.llm import ProviderDep
from app.models import Conversation, Message, PendingAction
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


async def get_action(
    body: ChatRequest,
    session: SessionDep,
    conversation: Annotated[Conversation, Depends(get_or_create_conversation)],
) -> PendingAction | None:
    """The card the patient answered. It must belong to this conversation."""
    if body.action is None:
        return None
    action = await session.get(PendingAction, body.action.id)
    if action is None or action.conversation_id != conversation.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found")
    return action


@router.post("/chat", response_class=EventSourceResponse)
async def chat(
    body: ChatRequest,
    session: SessionDep,
    provider: ProviderDep,
    embedder: EmbedderDep,
    settings: SettingsDep,
    clock: ClockDep,
    conversation: Annotated[Conversation, Depends(get_or_create_conversation)],
    action: Annotated[PendingAction | None, Depends(get_action)],
) -> AsyncIterator[ServerSentEvent]:
    async for event in stream_reply(
        session=session,
        provider=provider,
        embedder=embedder,
        settings=settings,
        clock=clock,
        conversation=conversation,
        user_text=body.message,
        ui_language=body.language,
        action=action,
        confirm=body.action is not None and body.action.decision == "confirm",
    ):
        yield event


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, session: SessionDep, settings: SettingsDep, clock: ClockDep
) -> ConversationOut:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    messages = list(
        await session.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        )
    )
    action_ids = [m.action_id for m in messages if m.action_id is not None]
    actions = {
        a.id: a
        for a in await session.scalars(
            select(PendingAction).where(PendingAction.id.in_(action_ids))
        )
    }
    clinic = Clinic(session, settings, clock())
    return ConversationOut.model_validate(
        {
            "id": conversation.id,
            "language": conversation.language,
            "created_at": conversation.created_at,
            "messages": [
                MessageOut.model_validate(
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "sources": m.sources,
                        "action_result": m.action_result,
                        "created_at": m.created_at,
                        "confirmation": confirmation_card(clinic, actions[m.action_id])
                        if m.action_id in actions
                        else None,
                    }
                )
                for m in messages
            ],
        }
    )
