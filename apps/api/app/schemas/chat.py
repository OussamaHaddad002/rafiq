import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Language = Literal["ar", "fr", "en"]


class ActionDecision(BaseModel):
    """The patient pressed Confirm or Cancel on a card."""

    id: uuid.UUID
    decision: Literal["confirm", "decline"]


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=4000)
    language: Language = "en"
    action: ActionDecision | None = None

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @model_validator(mode="after")
    def action_needs_conversation(self) -> Self:
        if self.action is not None and self.conversation_id is None:
            raise ValueError("an action belongs to an existing conversation")
        return self


class SourceOut(BaseModel):
    """A knowledge-base excerpt given to the model; `n` is its citation number, as in [n]."""

    n: int
    source: str
    title: str
    page: int | None
    section: str | None
    lang: str
    excerpt: str


class ConfirmationOut(BaseModel):
    """A Confirm / Cancel card for a pending booking, reschedule or cancellation."""

    action_id: uuid.UUID
    kind: Literal["book", "reschedule", "cancel"]
    status: str  # pending | confirmed | declined | expired | failed | superseded
    details: dict[str, Any]
    expires_at: datetime
    result: dict[str, Any] | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceOut] | None = None
    confirmation: ConfirmationOut | None = None
    action_result: dict[str, Any] | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    language: Language
    created_at: datetime
    messages: list[MessageOut]


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
