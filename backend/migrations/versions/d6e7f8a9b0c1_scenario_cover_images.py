"""scenario custom cover images

Revision ID: d6e7f8a9b0c1
Revises: c3d4e5f6a7b8
Create Date: 2026-10-09 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "scenario_cover_images",
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("scenario_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("scenario_cover_images")
