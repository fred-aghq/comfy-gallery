"""Add workflow_search_text column with pg_trgm GIN index.

Revision ID: 002
Revises: 001
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column(
        "media_files",
        sa.Column("workflow_search_text", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_media_files_workflow_search_trgm",
        "media_files",
        ["workflow_search_text"],
        postgresql_using="gin",
        postgresql_ops={"workflow_search_text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_media_files_workflow_search_trgm",
        table_name="media_files",
    )
    op.drop_column("media_files", "workflow_search_text")
