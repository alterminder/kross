"""scenario curated flag

Revision ID: c9f2a71b3e04
Revises: e2ebed744961
Create Date: 2026-09-30 14:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f2a71b3e04"
down_revision: str | Sequence[str] | None = "e2ebed744961"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("scenarios", sa.Column("curated", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("scenarios", "curated", server_default=None)  # the ORM supplies the default from now on
    # rows created by the seed: system org, author gone (or never set) at migration time
    op.execute(
        "UPDATE scenarios SET curated = true WHERE owner_id IS NULL AND org_id = (SELECT id FROM orgs WHERE is_system)"
    )
    op.drop_index("uq_scenarios_curated_slug", table_name="scenarios")
    op.create_index(
        "uq_scenarios_curated_slug",
        "scenarios",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("curated AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_scenarios_curated_slug", table_name="scenarios")
    op.create_index(
        "uq_scenarios_curated_slug",
        "scenarios",
        ["org_id", "slug"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NULL AND deleted_at IS NULL"),
    )
    op.drop_column("scenarios", "curated")
