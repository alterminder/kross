"""pin each sign-in session to the identity that authenticated it

Revision ID: h8b9c0d1e2f3
Revises: g7a8b9c0d1e2
Create Date: 2026-10-12 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h8b9c0d1e2f3"
down_revision: str | Sequence[str] | None = "g7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema. Existing rows keep identity_id NULL: those sessions fail admin closed until the user
    signs in again (admin rights follow the authenticating identity, not the account)."""
    op.add_column("auth_sessions", sa.Column("identity_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_auth_sessions_identity_id", "auth_sessions", "identities", ["identity_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_auth_sessions_identity_id", "auth_sessions", type_="foreignkey")
    op.drop_column("auth_sessions", "identity_id")
