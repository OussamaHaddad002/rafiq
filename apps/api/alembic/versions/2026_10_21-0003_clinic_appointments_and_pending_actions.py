"""clinic: doctors, schedules, appointments, pending actions, callbacks

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21 13:55:18.389281

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "doctors",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("specialty", sa.String(length=30), nullable=False),
        sa.Column("languages", postgresql.ARRAY(sa.String(length=2)), nullable=False),
        sa.Column("room", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctors")),
        sa.UniqueConstraint("slug", name=op.f("uq_doctors_slug")),
    )
    op.create_index(op.f("ix_doctors_specialty"), "doctors", ["specialty"], unique=False)
    op.create_table(
        "appointments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("booking_code", sa.String(length=12), nullable=False),
        sa.Column("doctor_id", sa.SmallInteger(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("patient_name", sa.String(length=120), nullable=False),
        sa.Column("patient_phone", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="booked", nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('booked', 'cancelled')", name=op.f("ck_appointments_status")
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_appointments_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f("fk_appointments_doctor_id_doctors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointments")),
        sa.UniqueConstraint("booking_code", name=op.f("uq_appointments_booking_code")),
    )
    op.create_index(op.f("ix_appointments_doctor_id"), "appointments", ["doctor_id"], unique=False)
    op.create_index(
        "uq_appointments_doctor_slot",
        "appointments",
        ["doctor_id", "starts_at"],
        unique=True,
        postgresql_where=sa.text("status = 'booked'"),
    )
    op.create_table(
        "callback_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("patient_name", sa.String(length=120), nullable=True),
        sa.Column("patient_phone", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_callback_requests_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_callback_requests")),
    )
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('book', 'reschedule', 'cancel')", name=op.f("ck_pending_actions_kind")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'declined', 'expired', 'failed', 'superseded')",
            name=op.f("ck_pending_actions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_pending_actions_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pending_actions")),
    )
    op.create_index(
        op.f("ix_pending_actions_conversation_id"),
        "pending_actions",
        ["conversation_id"],
        unique=False,
    )
    op.create_table(
        "schedules",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("doctor_id", sa.SmallInteger(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.CheckConstraint("start_time < end_time", name=op.f("ck_schedules_window")),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name=op.f("ck_schedules_weekday")),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["doctors.id"],
            name=op.f("fk_schedules_doctor_id_doctors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedules")),
    )
    op.create_index(op.f("ix_schedules_doctor_id"), "schedules", ["doctor_id"], unique=False)
    op.add_column(
        "messages", sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column("messages", sa.Column("action_id", sa.Uuid(), nullable=True))
    op.add_column(
        "messages",
        sa.Column("action_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_messages_action_id_pending_actions"),
        "messages",
        "pending_actions",
        ["action_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:

    op.drop_constraint(
        op.f("fk_messages_action_id_pending_actions"), "messages", type_="foreignkey"
    )
    op.drop_column("messages", "action_result")
    op.drop_column("messages", "action_id")
    op.drop_column("messages", "tool_calls")
    op.drop_index(op.f("ix_schedules_doctor_id"), table_name="schedules")
    op.drop_table("schedules")
    op.drop_index(op.f("ix_pending_actions_conversation_id"), table_name="pending_actions")
    op.drop_table("pending_actions")
    op.drop_table("callback_requests")
    op.drop_index(
        "uq_appointments_doctor_slot",
        table_name="appointments",
        postgresql_where=sa.text("status = 'booked'"),
    )
    op.drop_index(op.f("ix_appointments_doctor_id"), table_name="appointments")
    op.drop_table("appointments")
    op.drop_index(op.f("ix_doctors_specialty"), table_name="doctors")
    op.drop_table("doctors")
