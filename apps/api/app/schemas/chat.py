import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Language = Literal["ar", "fr", "en"]


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=4000)
    language: Language = "en"

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class SourceOut(BaseModel):
    """A knowledge-base excerpt given to the model; `n` is its citation number, as in [n]."""

    n: int
    source: str
    title: str
    page: int | None
    section: str | None
    lang: str
    excerpt: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceOut] | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    language: Language
    created_at: datetime
    messages: list[MessageOut]


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
