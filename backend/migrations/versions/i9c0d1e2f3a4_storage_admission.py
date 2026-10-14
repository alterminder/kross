"""Durable write admission buckets.

Revision ID: i9c0d1e2f3a4
Revises: h8b9c0d1e2f3
"""

import sqlalchemy as sa
from alembic import op

revision = "i9c0d1e2f3a4"
down_revision = "h8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_buckets",
        sa.Column("scope", sa.String(10), primary_key=True),
        sa.Column("scope_id", sa.Uuid(), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("writes", sa.BigInteger(), nullable=False),
        sa.Column("bytes_written", sa.BigInteger(), nullable=False),
    )
    # Existing data consumes capacity too; upgrading must not create a fresh allowance for it.
    op.execute("""
        INSERT INTO storage_buckets (scope, scope_id, day, writes, bytes_written)
        SELECT 'global', '00000000-0000-0000-0000-000000000000'::uuid, DATE '1970-01-01', 0,
            COALESCE(SUM(pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename))), 0)
        FROM pg_tables WHERE schemaname = 'public' AND tablename != 'storage_buckets'
    """)
    op.execute("""
        INSERT INTO storage_buckets (scope, scope_id, day, writes, bytes_written)
        SELECT scope, scope_id, DATE '1970-01-01', 0, SUM(size)
        FROM (
            SELECT 'user' AS scope, v.created_by AS scope_id, pg_column_size(v.content) + 1024 AS size
            FROM scenario_versions v WHERE v.created_by IS NOT NULL
            UNION ALL
            SELECT 'org', s.org_id, pg_column_size(v.content) + 1024
            FROM scenario_versions v JOIN scenarios s ON s.id = v.scenario_id
            UNION ALL
            SELECT 'user', created_by, pg_column_size(overrides) + 1024
            FROM rule_versions WHERE created_by IS NOT NULL
            UNION ALL
            SELECT 'org', org_id, pg_column_size(overrides) + 1024 FROM rule_versions
            UNION ALL
            SELECT 'user', user_id, pg_column_size(s) + 1024 FROM play_sessions s
            UNION ALL
            SELECT 'org', org_id, pg_column_size(s) + 1024 FROM play_sessions s
            UNION ALL
            SELECT 'user', s.user_id, pg_column_size(t) + 1024
            FROM turns t JOIN play_sessions s ON s.id = t.session_id
            UNION ALL
            SELECT 'org', s.org_id, pg_column_size(t) + 1024
            FROM turns t JOIN play_sessions s ON s.id = t.session_id
        ) existing_data
        GROUP BY scope, scope_id
    """)


def downgrade() -> None:
    op.drop_table("storage_buckets")
