"""The migrations build exactly the schema the models describe."""

import asyncio

import asyncpg
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from nlab.db.models import Base
from tests.api.conftest import TEST_URL, _ensure_database, alembic_config


def test_the_migrations_match_the_models(database_url):
    async def differences():
        engine = create_async_engine(database_url)
        async with engine.connect() as connection:
            found = await connection.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
            )
        await engine.dispose()
        return found

    assert asyncio.run(differences()) == []


def test_the_rule_version_backfill():
    """e2ebed744961 numbers pre-existing rule_versions rows per org (oldest first) instead of failing on them."""
    url = TEST_URL + "_backfill"
    server = url.replace("postgresql+asyncpg://", "postgresql://")
    asyncio.run(_ensure_database(url))
    config = alembic_config(url)
    command.downgrade(config, "base")  # reset a leftover from a previous run; upgrade() never moves backwards
    command.upgrade(config, "b94fb4401d3d")  # the revision before numbered rule versions

    async def insert_rows() -> None:
        connection = await asyncpg.connect(server)
        try:
            org = await connection.fetchval(
                "INSERT INTO orgs (id, name, is_system) VALUES (gen_random_uuid(), 'Backfill', false) RETURNING id"
            )
            other = await connection.fetchval(
                "INSERT INTO orgs (id, name, is_system) VALUES (gen_random_uuid(), 'Other', false) RETURNING id"
            )
            for org_id in (org, org, other):
                await connection.execute(
                    "INSERT INTO rule_versions (id, org_id, overrides) VALUES (gen_random_uuid(), $1, '{}')", org_id
                )
        finally:
            await connection.close()

    async def numbered() -> list[int]:
        connection = await asyncpg.connect(server)
        try:
            org = await connection.fetchval("SELECT id FROM orgs WHERE name = 'Backfill'")
            rows = await connection.fetch("SELECT number FROM rule_versions WHERE org_id = $1 ORDER BY number", org)
            return [row["number"] for row in rows]
        finally:
            await connection.close()

    asyncio.run(insert_rows())
    command.upgrade(config, "head")
    assert asyncio.run(numbered()) == [1, 2]


def test_the_custom_cover_backfill():
    """f6a7b8c9d0e1 marks every scenario with a painted cover image as custom (downgrade: back to field)."""
    url = TEST_URL + "_covers"
    server = url.replace("postgresql+asyncpg://", "postgresql://")
    asyncio.run(_ensure_database(url))
    config = alembic_config(url)
    command.downgrade(config, "base")  # reset a leftover from a previous run
    command.upgrade(config, "d6e7f8a9b0c1")  # the revision before the backfill

    async def insert_rows() -> None:
        connection = await asyncpg.connect(server)
        try:
            org = await connection.fetchval(
                "INSERT INTO orgs (id, name, is_system) VALUES (gen_random_uuid(), 'Covers', false) RETURNING id"
            )
            painted = await connection.fetchval(
                "INSERT INTO scenarios (id, org_id, slug, title, cover, visibility, curated, current_version)"
                " VALUES (gen_random_uuid(), $1, 'painted', 'Painted', 'field', 'private', false, 1) RETURNING id",
                org,
            )
            await connection.execute(
                "INSERT INTO scenarios (id, org_id, slug, title, cover, visibility, curated, current_version)"
                " VALUES (gen_random_uuid(), $1, 'themed', 'Themed', 'camp', 'private', false, 1)",
                org,
            )
            await connection.execute(
                "INSERT INTO scenario_cover_images (scenario_id, data) VALUES ($1, $2)", painted, b"\x00"
            )
        finally:
            await connection.close()

    async def covers() -> dict[str, str]:
        connection = await asyncpg.connect(server)
        try:
            rows = await connection.fetch("SELECT slug, cover FROM scenarios ORDER BY slug")
            return {row["slug"]: row["cover"] for row in rows}
        finally:
            await connection.close()

    asyncio.run(insert_rows())
    command.upgrade(config, "head")
    assert asyncio.run(covers()) == {"painted": "custom", "themed": "camp"}
    command.downgrade(config, "d6e7f8a9b0c1")  # runs the backfill's own downgrade
    assert asyncio.run(covers()) == {"painted": "field", "themed": "camp"}
