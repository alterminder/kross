"""mark painted covers as custom

Revision ID: f6a7b8c9d0e1
Revises: d6e7f8a9b0c1
Create Date: 2026-10-09 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Every scenario with a painted cover image now says so on its card."""
    op.execute("UPDATE scenarios SET cover = 'custom' WHERE id IN (SELECT scenario_id FROM scenario_cover_images)")


def downgrade() -> None:
    """Back to the theme cover; the paintings themselves stay untouched."""
    op.execute("UPDATE scenarios SET cover = 'field' WHERE cover = 'custom'")
