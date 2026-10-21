import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

SPECIALTIES = (
    "general_medicine",
    "cardiology",
    "dentistry",
    "pediatrics",
    "dermatology",
    "gynecology",
    "ophthalmology",
)


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    specialty: Mapped[str] = mapped_column(String(30), index=True)
    languages: Mapped[list[str]] = mapped_column(ARRAY(String(2)))
    room: Mapped[str] = mapped_column(String(50))


class Schedule(Base):
    """A weekly consultation window, e.g. Monday 08:00-14:00, in clinic time."""

    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint("start_time < end_time", name="window"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("status IN ('booked', 'cancelled')", name="status"),
        # One booked appointment per doctor and start time, enforced by the database so two
        # patients confirming the same slot at the same moment cannot both succeed.
        Index(
            "uq_appointments_doctor_slot",
            "doctor_id",
            "starts_at",
            unique=True,
            postgresql_where=text("status = 'booked'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    booking_code: Mapped[str] = mapped_column(String(12), unique=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    patient_name: Mapped[str] = mapped_column(String(120))
    patient_phone: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), server_default="booked")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )


class PendingAction(TimestampMixin, Base):
    """A write (book / reschedule / cancel) proposed by the agent, run only on patient confirm."""

    __tablename__ = "pending_actions"
    __table_args__ = (
        CheckConstraint("kind IN ('book', 'reschedule', 'cancel')", name="kind"),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'declined', 'expired', 'failed', 'superseded')",
            name="status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(12))
    # What to execute (ids, UTC times) and what to show on the card (names, local times).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(12), server_default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CallbackRequest(TimestampMixin, Base):
    __tablename__ = "callback_requests"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(Text)
    patient_name: Mapped[str | None] = mapped_column(String(120))
    patient_phone: Mapped[str | None] = mapped_column(String(20))
