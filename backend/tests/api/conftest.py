"""API test fixtures: a real Postgres (docker compose -f compose.dev.yml up -d db), migrated from scratch once per
run and emptied before each test, and HTTP clients that sign in through fake identity providers."""

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[2]
TEST_URL = os.environ.get("NLAB_TEST_DATABASE_URL", "postgresql+asyncpg://nlab:nlab@localhost:5433/nlab_test")


async def _ensure_database(url: str) -> None:
    server, name = url.replace("postgresql+asyncpg://", "postgresql://").rsplit("/", 1)
    try:
        connection = await asyncpg.connect(f"{server}/postgres")
    except OSError as exc:
        raise RuntimeError(f"No Postgres at {server}: run `docker compose -f compose.dev.yml up -d db`") from exc
    try:
        if not await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    asyncio.run(_ensure_database(TEST_URL))
    config = alembic_config(TEST_URL)
    command.upgrade(config, "head")
    command.downgrade(config, "base")  # a fresh database also proves the downgrade path works
    command.upgrade(config, "head")
    return TEST_URL


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def app(database_url: str) -> AsyncIterator[FastAPI]:
    from nlab.api.app import create_app  # imported here so the migration test runs before the app exists
    from nlab.api.settings import Settings
    from tests.api.fakes import FakeProvider
    from tests.llm.fakes import FakeProvider as FakeLLM

    settings = Settings(
        _env_file=None,
        database_url=database_url,
        secret_key="test-secret",
        cookie_secure=False,
        public_url="http://test",
        superadmin_identities={"fake": ["root"]},  # platform-admin policy: provider + stable subject
    )
    application = create_app(
        settings, providers={"fake": FakeProvider("fake"), "fake2": FakeProvider("fake2")}, llm=(FakeLLM([]), None)
    )
    async with application.router.lifespan_context(application):
        async with application.state.engine.begin() as connection:
            await connection.execute(
                text(
                    "TRUNCATE users, orgs, llm_calls, budget_reservations, daily_admissions, storage_buckets "
                    "RESTART IDENTITY CASCADE"
                )
            )
        yield application


@pytest.fixture
async def new_client(app: FastAPI) -> AsyncIterator[Callable[[], AsyncClient]]:
    """A factory: each client is one browser with its own cookies."""
    clients: list[AsyncClient] = []

    def make() -> AsyncClient:
        client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers={"X-Requested-With": "nlab"}
        )
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()
