"""Durable write admission contains database growth across parallel requests."""

import asyncio

import pytest

from tests.api.support import sign_in
from tests.api.test_scenarios import draft

pytestmark = pytest.mark.anyio


async def test_parallel_org_creation_cannot_exceed_user_write_cap(app, new_client):
    client = new_client()
    await sign_in(client, "writer", "writer@example.org")
    app.state.settings = app.state.settings.model_copy(update={"limit_user_writes_per_day": 3})  # sign-in + two writes
    replies = await asyncio.gather(*[client.post("/api/orgs", json={"name": f"Org {i}"}) for i in range(6)])
    assert sorted(reply.status_code for reply in replies) == [201, 201, 429, 429, 429, 429]


async def test_deleting_a_scenario_does_not_replenish_write_allowance(app, new_client):
    client = new_client()
    await sign_in(client, "writer", "writer@example.org")
    app.state.settings = app.state.settings.model_copy(update={"limit_user_writes_per_day": 2})  # sign-in + one write
    created = await client.post("/api/scenarios", json={"content": draft()})
    assert created.status_code == 201, created.text
    assert (await client.delete(f"/api/scenarios/{created.json()['id']}")).status_code == 204
    refused = await client.post("/api/scenarios", json={"content": draft()})
    assert refused.status_code == 429


async def test_lifetime_write_bytes_limit_applies_across_new_orgs(app, new_client):
    client = new_client()
    await sign_in(client, "writer", "writer@example.org")
    app.state.settings = app.state.settings.model_copy(update={"limit_user_storage_bytes": 8192 + 1024})
    assert (await client.post("/api/orgs", json={"name": "First"})).status_code == 201
    refused = await client.post("/api/orgs", json={"name": "Second"})
    assert refused.status_code == 429
    assert "storage" in refused.json()["detail"].lower()


async def test_new_accounts_and_auth_sessions_share_global_storage_admission(app, new_client):
    app.state.settings = app.state.settings.model_copy(update={"limit_total_writes_per_day": 2})
    responses = []
    for subject in ("one", "two", "three"):
        responses.append(await new_client().get("/api/auth/fake/callback", params={"sub": subject}))
    assert [response.status_code for response in responses] == [303, 303, 429]
