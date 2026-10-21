"""store missing JSON values as SQL NULL, not JSON null

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21

Earlier rows saved Python None as the JSON value `null`, so `IS NULL` queries missed them.
The columns now use `none_as_null=True`; this converts the existing rows.

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = {
    "messages": ("sources", "tool_calls", "action_result"),
    "pending_actions": ("result",),
}


def upgrade() -> None:
    for table, columns in COLUMNS.items():
        for column in columns:
            op.execute(f"UPDATE {table} SET {column} = NULL WHERE {column} = 'null'::jsonb")


def downgrade() -> None:
    # Nothing to undo: SQL NULL is the correct representation either way.
    pass
