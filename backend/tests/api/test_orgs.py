import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from nlab.db.errors import Conflict
from nlab.db.models import Membership, Org, Role
from nlab.db.orgs import context_for, set_role
from tests.api.support import card_id, count, join, org_with_admin, say, seed_curated, sign_in, start_play, use_model

pytestmark = pytest.mark.anyio


async def test_any_signed_in_user_can_start_an_org_and_lands_in_it(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    created = await alice.post("/api/orgs", json={"name": "Field Trainers"})
    assert created.status_code == 201, created.text
    me = (await alice.get("/api/me")).json()
    assert me["active_org"]["name"] == "Field Trainers"
    assert me["active_org"]["role"] == "admin" and not me["active_org"]["personal"]
    assert [org["personal"] for org in me["orgs"]] == [True, False]  # her personal space, then the new org


async def test_the_creator_trains_their_org(app, new_client):
    """The creator invites a trainee, who plays solo; the creator watches that session."""
    use_model(app)
    await seed_curated(app)
    trainer = new_client()
    await sign_in(trainer, "trainer", "trainer@example.org")
    assert (await trainer.post("/api/orgs", json={"name": "Field Trainers"})).status_code == 201
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, trainer)
    session = await start_play(bob, await card_id(bob, "camp"))
    await say(bob, session["id"], "Hello.")
    progress = await trainer.get(f"/api/sessions/{session['id']}/progress")
    assert progress.status_code == 200, progress.text
    assert progress.json()["player"] == "bob"


async def test_a_blank_org_name_is_refused(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.post("/api/orgs", json={"name": "   "})).status_code == 422
    assert await count(app, Org) == 1  # only alice's personal space


async def test_a_user_can_switch_only_to_their_own_orgs(app, new_client):
    admin, org_id = await org_with_admin(new_client)
    stranger = new_client()
    await sign_in(stranger, "bob", "bob@example.org")
    assert (await stranger.post("/api/orgs/active", json={"org_id": org_id})).status_code == 404
    personal = next(org for org in (await admin.get("/api/me")).json()["orgs"] if org["personal"])
    assert (await admin.post("/api/orgs/active", json={"org_id": personal["id"]})).status_code == 204
    assert (await admin.get("/api/me")).json()["active_org"]["id"] == personal["id"]


async def test_only_admins_see_members(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    assert (await bob.get("/api/org/members")).status_code == 403
    roles = {member["display_name"]: member["role"] for member in (await admin.get("/api/org/members")).json()}
    assert roles["bob"] == "member" and roles["admin-red-cross-delegation"] == "admin"


async def test_removing_a_member_revokes_their_access_at_once(app, new_client):
    admin, org_id = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    me = (await bob.get("/api/me")).json()
    assert me["active_org"]["id"] == org_id
    assert (await admin.delete(f"/api/org/members/{me['id']}")).status_code == 204
    after = (await bob.get("/api/me")).json()
    assert after["active_org"]["personal"] and org_id not in {org["id"] for org in after["orgs"]}


async def test_an_org_keeps_at_least_one_admin(app, new_client):
    admin, _ = await org_with_admin(new_client)
    admin_id = (await admin.get("/api/me")).json()["id"]
    assert (await admin.delete(f"/api/org/members/{admin_id}")).status_code == 409
    assert (await admin.patch(f"/api/org/members/{admin_id}", json={"role": "member"})).status_code == 409


async def test_an_admin_cannot_demote_themselves_while_a_member_remains(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    admin_id = (await admin.get("/api/me")).json()["id"]
    assert (await admin.patch(f"/api/org/members/{admin_id}", json={"role": "member"})).status_code == 409


async def test_an_admin_can_promote_a_member(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    bob_id = (await bob.get("/api/me")).json()["id"]
    assert (await admin.patch(f"/api/org/members/{bob_id}", json={"role": "admin"})).status_code == 204
    assert (await bob.get("/api/org/members")).status_code == 200


async def test_an_admin_cannot_reach_another_orgs_members(app, new_client):
    admin_a, _ = await org_with_admin(new_client, "Org A")
    admin_b, _ = await org_with_admin(new_client, "Org B")
    carol = new_client()
    await sign_in(carol, "carol", "carol@example.org")
    await join(carol, admin_b)
    carol_id = (await carol.get("/api/me")).json()["id"]
    assert carol_id not in {member["user_id"] for member in (await admin_a.get("/api/org/members")).json()}
    assert (await admin_a.delete(f"/api/org/members/{carol_id}")).status_code == 404
    assert (await admin_a.patch(f"/api/org/members/{carol_id}", json={"role": "admin"})).status_code == 404


async def test_nobody_leaves_a_personal_space(app, new_client):
    alice = new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.delete(f"/api/org/members/{me['id']}")).status_code == 409


async def test_two_admins_cannot_demote_each_other_at_the_same_time(app, new_client):
    """The second transaction waits on the org row lock and is refused after re-counting: one admin survives."""
    admin, org_id = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    admin_id = (await admin.get("/api/me")).json()["id"]
    bob_id = (await bob.get("/api/me")).json()["id"]
    assert (await admin.patch(f"/api/org/members/{bob_id}", json={"role": "admin"})).status_code == 204

    org = uuid.UUID(org_id)
    maker = app.state.sessionmaker
    async with maker() as s1, maker() as s2:
        c1 = await context_for(s1, uuid.UUID(admin_id), org)
        c2 = await context_for(s2, uuid.UUID(bob_id), org)
        await set_role(s1, c1, uuid.UUID(bob_id), Role.member)  # admin demotes bob
        await s1.flush()
        demoting = asyncio.create_task(set_role(s2, c2, uuid.UUID(admin_id), Role.member))  # bob demotes admin
        await asyncio.sleep(0.2)  # let s2 block on the org row lock
        await s1.commit()
        with pytest.raises(Conflict):
            await demoting
        await s2.rollback()
    async with maker() as db:
        admins = await db.scalar(
            select(func.count()).select_from(Membership).where(Membership.org_id == org, Membership.role == Role.admin)
        )
    assert admins == 1
