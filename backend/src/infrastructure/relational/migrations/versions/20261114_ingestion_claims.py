"""Atomic ingestion admission without modifying existing document/job rows."""

import sqlalchemy as sa
from alembic import op

revision = "20261114_ingestion_claims"
down_revision = "20261107_task_requirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_claims",
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("job_id", sa.String(), nullable=False, unique=True),
    )


def downgrade() -> None:
    op.drop_table("ingestion_claims")
