"""guest users

Revision ID: a7c3d9e1f2b4
Revises: f1a2b3c4d5e6
Create Date: 2026-10-02 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3d9e1f2b4"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("is_guest", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("users", "is_guest", server_default=None)  # the ORM supplies the default from now on


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "is_guest")
