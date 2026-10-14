"""budget reservations and durable daily admissions

Revision ID: g7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-12 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "budget_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("reserved_in", sa.BigInteger(), nullable=False),
        sa.Column("reserved_out", sa.BigInteger(), nullable=False),
        sa.Column("used_in", sa.BigInteger(), nullable=False),
        sa.Column("used_out", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_budget_reservations_user_id"), "budget_reservations", ["user_id"], unique=False)
    op.create_index(op.f("ix_budget_reservations_org_id"), "budget_reservations", ["org_id"], unique=False)
    op.create_index(op.f("ix_budget_reservations_session_id"), "budget_reservations", ["session_id"], unique=False)
    op.create_index(op.f("ix_budget_reservations_created_at"), "budget_reservations", ["created_at"], unique=False)
    op.create_table(
        "daily_admissions",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("day", "scope", "key"),
    )
    op.add_column("llm_calls", sa.Column("reservation_id", sa.Uuid(), nullable=True))
    # Backfill today's (and every past day's) admissions from the existing rows, so this upgrade never resets a
    # same-day quota: session starts from play_sessions, guest signups from users, coach questions from the ledger.
    op.execute(
        "INSERT INTO daily_admissions (day, scope, key, count) "
        "SELECT (created_at AT TIME ZONE 'UTC')::date, 'session_start', user_id::text, count(*) "
        "FROM play_sessions GROUP BY 1, 3"
    )
    op.execute(
        "INSERT INTO daily_admissions (day, scope, key, count) "
        "SELECT (created_at AT TIME ZONE 'UTC')::date, 'guest_signup', 'global', count(*) "
        "FROM users WHERE is_guest GROUP BY 1"
    )
    op.execute(
        "INSERT INTO daily_admissions (day, scope, key, count) "
        "SELECT '1970-01-01', 'coach_question', session_id::text, count(*) "
        "FROM llm_calls WHERE role = 'scope' AND session_id IS NOT NULL GROUP BY 3"  # lifetime per session
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("llm_calls", "reservation_id")
    op.drop_table("daily_admissions")
    op.drop_index(op.f("ix_budget_reservations_created_at"), table_name="budget_reservations")
    op.drop_index(op.f("ix_budget_reservations_session_id"), table_name="budget_reservations")
    op.drop_index(op.f("ix_budget_reservations_org_id"), table_name="budget_reservations")
    op.drop_index(op.f("ix_budget_reservations_user_id"), table_name="budget_reservations")
    op.drop_table("budget_reservations")
