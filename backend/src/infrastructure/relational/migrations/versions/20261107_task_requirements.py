"""Persist chunk provenance, structured tables, and conversation history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261107_task_requirements"
down_revision: str | None = "158962a00ee8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}")
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("conversations")
    with op.batch_alter_table("chunks") as batch:
        batch.drop_column("metadata_json")
