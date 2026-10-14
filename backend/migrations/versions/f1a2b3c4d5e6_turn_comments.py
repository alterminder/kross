"""turn comments

Revision ID: f1a2b3c4d5e6
Revises: d5354e0d7745
Create Date: 2026-10-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "d5354e0d7745"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "turn_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["play_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_turn_comments_session_id"), "turn_comments", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_turn_comments_session_id"), table_name="turn_comments")
    op.drop_table("turn_comments")
