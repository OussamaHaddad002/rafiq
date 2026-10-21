import uuid
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # UI language when the conversation started; patients may still write in another one.
    language: Mapped[str] = mapped_column(String(2))


class Message(TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="role"),)

    # Identity PK doubles as the ordering key within a conversation.
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # Assistant messages: the documents given to the model, numbered as cited in `content`.
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
