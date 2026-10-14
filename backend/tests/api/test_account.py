import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from nlab.db.accounts import delete_account
from nlab.db.errors import Conflict
from nlab.db.invites import accept_invite
from nlab.db.models import AuthSession, Identity, Membership, Org, User
from tests.api.support import SUPERADMIN, count, draft, join, org_with_admin, seed_curated, sign_in, token_of

pytestmark = pytest.mark.anyio


async def test_deleting_an_account_removes_everything_personal(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.delete("/api/me")).status_code == 204
    assert (await alice.get("/api/me")).status_code == 401
    for model in (User, Identity, Org, Membership, AuthSession):
        assert await count(app, model) == 0, model.__name__


async def test_a_member_who_deletes_their_account_leaves_the_org(app, new_client):
    admin, org_id = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    assert (await bob.delete("/api/me")).status_code == 204
    assert "bob" not in {member["display_name"] for member in (await admin.get("/api/org/members")).json()}
    assert (await admin.get("/api/me")).json()["active_org"]["id"] == org_id


async def test_the_only_admin_of_a_shared_org_cannot_delete_their_account(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)  # the org has another member, so it cannot go away with the account
    refused = await admin.delete("/api/me")
    assert refused.status_code == 409 and "only admin" in refused.json()["detail"]


async def test_a_sole_member_org_is_deleted_with_the_account(app, new_client):
    """A self-created org nobody else joined is no obstacle: it is deleted together with the account."""
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.post("/api/orgs", json={"name": "Solo trainers"})).status_code == 201
    assert (await alice.delete("/api/me")).status_code == 204
    assert await count(app, Org) == 0  # her personal space and her org went with her


async def test_an_admin_with_a_successor_can_delete_their_account(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    bob_id = (await bob.get("/api/me")).json()["id"]
    assert (await admin.patch(f"/api/org/members/{bob_id}", json={"role": "admin"})).status_code == 204
    assert (await admin.delete("/api/me")).status_code == 204
    assert (await admin.get("/api/me")).status_code == 401


async def test_R2_a_join_that_commits_first_blocks_a_sole_member_org_deletion(app, new_client):
    """accept_invite locks the org row (FOR NO KEY UPDATE) before it adds its membership, so a join that commits
    first makes the deletion re-count two members and refuse, instead of silently erasing the accepted join."""
    alice = new_client()
    alice_me = await sign_in(alice, "alice", "alice@example.org")
    await alice.post("/api/orgs", json={"name": "Solo trainers"})
    org_id = uuid.UUID((await alice.get("/api/me")).json()["active_org"]["id"])
    token = token_of((await alice.post("/api/org/invites", json={})).json()["url"])
    bob = new_client()
    bob_me = await sign_in(bob, "bob", "bob@example.org")

    maker = app.state.sessionmaker
    async with maker() as accepting, maker() as deleting_db:
        await accept_invite(accepting, token, uuid.UUID(bob_me["id"]))  # bob joins, holds the org lock
        deleting = asyncio.create_task(delete_account(deleting_db, uuid.UUID(alice_me["id"])))
        await asyncio.sleep(0.2)  # the deletion waits on the org lock
        await accepting.commit()
        with pytest.raises(Conflict):
            await asyncio.wait_for(deleting, timeout=10)
        await deleting_db.rollback()
    async with maker() as db:
        assert await db.get(Org, org_id) is not None
        assert await db.get(Membership, (uuid.UUID(bob_me["id"]), org_id)) is not None


async def test_two_admins_cannot_both_delete_their_accounts_at_once(app, new_client):
    """The second deletion waits on the org lock, re-counts and is refused: the org keeps one admin."""
    admin, org_id = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    carol = new_client()  # a third member: the org stays, so the last admin cannot go
    await sign_in(carol, "carol", "carol@example.org")
    await join(carol, admin)
    bob_id = (await bob.get("/api/me")).json()["id"]
    assert (await admin.patch(f"/api/org/members/{bob_id}", json={"role": "admin"})).status_code == 204
    admin_id = uuid.UUID((await admin.get("/api/me")).json()["id"])

    maker = app.state.sessionmaker
    async with maker() as s1, maker() as s2:
        await delete_account(s1, admin_id)  # the admin deletes, holds the org lock
        deleting = asyncio.create_task(delete_account(s2, uuid.UUID(bob_id)))
        await asyncio.sleep(0.2)  # let s2 block on the org lock
        await s1.commit()
        with pytest.raises(Conflict):
            await asyncio.wait_for(deleting, timeout=10)
        await s2.rollback()
    async with maker() as db:
        admins = await db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.org_id == uuid.UUID(org_id), Membership.role == "admin")
        )
    assert admins == 1


async def test_R1_two_ownerless_org_scenarios_with_one_slug_do_not_block_account_deletion(app, new_client):
    """One brief converts to the same content id for two members: after both authors delete their
    accounts, two ownerless rows share (org, slug) and neither deletion may fail on a uniqueness clash."""
    admin, _ = await org_with_admin(new_client)
    clients = []
    for sub in ("alice", "bob"):
        client = new_client()
        await sign_in(client, sub, f"{sub}@example.org")
        await join(client, admin)
        made = (await client.post("/api/scenarios", json={"content": draft(f"{sub}'s", "camp_access")})).json()
        assert (await client.post(f"/api/scenarios/{made['id']}/submit")).status_code == 204
        assert (
            await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})
        ).status_code == 204
        clients.append(client)
    assert (await clients[0].delete("/api/me")).status_code == 204
    second = await clients[1].delete("/api/me")
    assert second.status_code == 204, f"bob cannot delete his account: {second.status_code} {second.text}"


async def test_R1b_a_published_scenario_with_a_curated_slug_does_not_block_its_authors_account_deletion(
    app, new_client
):
    """a superadmin's published copy of a curated slug lives beside the curated row in the system
    org; deleting the author's account must not collide with the curated row."""
    await seed_curated(app)
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    made = (await root.post("/api/scenarios", json={"content": draft("s01 v2 draft", "s01_idp_camp_access")})).json()
    assert (
        await root.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "public"})
    ).status_code == 204
    gone = await root.delete("/api/me")
    assert gone.status_code == 204, f"root cannot delete their account: {gone.status_code} {gone.text}"
