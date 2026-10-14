import asyncio
import uuid
from datetime import timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from nlab.db.accounts import delete_account
from nlab.db.auth_sessions import utcnow
from nlab.db.errors import Gone
from nlab.db.invites import accept_invite
from nlab.db.models import Invite, Membership, Org, User
from tests.api.support import join, org_with_admin, sign_in, token_of

pytestmark = pytest.mark.anyio


async def make_invite(admin, **body):
    made = await admin.post("/api/org/invites", json=body)
    assert made.status_code == 201, made.text
    return made.json()


class FakeDBError(Exception):
    """Stands in for the asyncpg error the SQLAlchemy adapter puts in IntegrityError.orig."""

    def __init__(self, message: str, sqlstate: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


async def test_an_invite_link_joins_as_member_after_the_notice(app, new_client):
    admin, org_id = await org_with_admin(new_client)
    invite = await make_invite(admin, days=3, max_uses=2)
    assert invite["url"].startswith("http://test/invite#") and invite["max_uses"] == 2 and invite["role"] == "member"
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    token = token_of(invite["url"])
    preview = (await bob.post("/api/invites/preview", json={"token": token})).json()
    assert preview["org_name"] == "Red Cross Delegation" and preview["problem"] is None
    assert not preview["already_member"] and "can see and steer your practice sessions" in preview["notice"]
    refused = await bob.post("/api/invites/accept", json={"token": token, "acknowledged": False})
    assert refused.status_code == 422
    joined = await bob.post("/api/invites/accept", json={"token": token, "acknowledged": True})
    assert joined.json()["org_id"] == org_id
    active = (await bob.get("/api/me")).json()["active_org"]
    assert active == {"id": org_id, "name": "Red Cross Delegation", "role": "member", "personal": False}


async def test_opening_an_invite_needs_sign_in(app, new_client):
    admin, _ = await org_with_admin(new_client)
    invite = await make_invite(admin)
    assert (await new_client().post("/api/invites/preview", json={"token": token_of(invite["url"])})).status_code == 401


async def test_accepting_twice_uses_one_place(app, new_client):
    admin, _ = await org_with_admin(new_client)
    token = token_of((await make_invite(admin, max_uses=1))["url"])
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    for _ in range(2):
        assert (await bob.post("/api/invites/accept", json={"token": token, "acknowledged": True})).status_code == 200
    carol = new_client()
    await sign_in(carol, "carol", "carol@example.org")
    assert (await carol.post("/api/invites/accept", json={"token": token, "acknowledged": True})).status_code == 410


async def test_a_revoked_invite_is_gone(app, new_client):
    admin, _ = await org_with_admin(new_client)
    invite = await make_invite(admin)
    assert (await admin.delete(f"/api/org/invites/{invite['id']}")).status_code == 204
    assert invite["id"] not in {item["id"] for item in (await admin.get("/api/org/invites")).json()}
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    token = token_of(invite["url"])
    assert (await bob.post("/api/invites/preview", json={"token": token})).json()["problem"] == "revoked"
    assert (await bob.post("/api/invites/accept", json={"token": token, "acknowledged": True})).status_code == 410


async def test_an_expired_invite_is_gone(app, new_client):
    admin, _ = await org_with_admin(new_client)
    invite = await make_invite(admin)
    async with app.state.sessionmaker() as db:
        await db.execute(update(Invite).values(expires_at=utcnow() - timedelta(minutes=1)))
        await db.commit()
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    token = token_of(invite["url"])
    assert (await bob.post("/api/invites/preview", json={"token": token})).json()["problem"] == "expired"
    assert (await bob.post("/api/invites/accept", json={"token": token, "acknowledged": True})).status_code == 410


async def test_members_cannot_invite(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    assert (await bob.post("/api/org/invites", json={})).status_code == 403


async def test_a_personal_space_has_no_invites(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.post("/api/org/invites", json={})).status_code == 409


async def test_an_admin_cannot_revoke_another_orgs_invite(app, new_client):
    admin_a, _ = await org_with_admin(new_client, "Org A")
    admin_b, _ = await org_with_admin(new_client, "Org B")
    invite_b = await make_invite(admin_b)
    assert (await admin_a.delete(f"/api/org/invites/{invite_b['id']}")).status_code == 404


async def test_an_admin_sees_only_their_own_orgs_invites(app, new_client):
    admin_a, _ = await org_with_admin(new_client, "Org A")
    admin_b, _ = await org_with_admin(new_client, "Org B")
    invite_b = await make_invite(admin_b)
    seen_a = {item["id"] for item in (await admin_a.get("/api/org/invites")).json()}
    seen_b = {item["id"] for item in (await admin_b.get("/api/org/invites")).json()}
    assert invite_b["id"] not in seen_a and invite_b["id"] in seen_b


async def test_the_last_place_in_an_invite_cannot_be_taken_twice(app, new_client):
    """Two sessions race for the one place: the second waits on the row lock and is refused after the first."""
    admin, _ = await org_with_admin(new_client)
    token = token_of((await make_invite(admin, max_uses=1))["url"])
    first = await sign_in(new_client(), "bob", "bob@example.org")
    second = await sign_in(new_client(), "carol", "carol@example.org")
    maker = app.state.sessionmaker
    async with maker() as s1, maker() as s2:
        await accept_invite(s1, token, uuid.UUID(first["id"]))  # takes the one place, holds the org lock
        racing = asyncio.create_task(accept_invite(s2, token, uuid.UUID(second["id"])))
        await asyncio.sleep(0.2)  # let s2 block on the first's locks
        await s1.commit()
        with pytest.raises(Gone):
            await racing
        await s2.rollback()


async def test_an_unknown_token_is_404(app, new_client):
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    assert (await bob.post("/api/invites/preview", json={"token": "not-a-token"})).status_code == 404


async def test_a_database_conflict_becomes_a_409(app, new_client, monkeypatch):
    """A lost race (say a double-clicked accept hitting the membership key) is a 409 with a generic message."""
    admin, _ = await org_with_admin(new_client)
    token = token_of((await make_invite(admin))["url"])
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")

    async def boom(*args: Any, **kwargs: Any) -> Org:
        raise IntegrityError("INSERT INTO memberships ...", {}, FakeDBError("duplicate key value", "23505"))

    monkeypatch.setattr("nlab.api.invites.accept_invite", boom)
    got = await bob.post("/api/invites/accept", json={"token": token, "acknowledged": True})
    assert got.status_code == 409 and got.json() == {"detail": "That change conflicts with the current state"}


async def test_a_database_bug_stays_a_500(app, new_client, monkeypatch):
    """Only lost races become 409: a NOT NULL violation is a code bug and must surface as a 500."""
    admin, _ = await org_with_admin(new_client)
    token = token_of((await make_invite(admin))["url"])
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")

    async def broken(*args: Any, **kwargs: Any) -> Org:
        raise IntegrityError("INSERT INTO orgs ...", {}, FakeDBError("null value in column", "23502"))

    monkeypatch.setattr("nlab.api.invites.accept_invite", broken)
    plain = AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={"X-Requested-With": "nlab"},
    )
    plain.cookies.set("nlab_session", bob.cookies["nlab_session"])
    got = await plain.post("/api/invites/accept", json={"token": token, "acknowledged": True})
    await plain.aclose()
    assert got.status_code == 500 and "conflicts" not in got.text


async def test_invite_tokens_are_stored_hashed(app, new_client):
    admin, _ = await org_with_admin(new_client)
    token = token_of((await make_invite(admin))["url"])
    async with app.state.sessionmaker() as db:
        hashes = set(await db.scalars(select(Invite.token_hash)))
    assert token not in hashes and all(len(value) == 64 for value in hashes)


async def test_deleting_an_account_does_not_deadlock_with_invite_acceptance(app, new_client):
    """accept_invite and delete_account both lock the org row (FOR NO KEY UPDATE) before anything else, so the
    accept serialises behind the delete instead of the two waiting on each other's rows and Postgres killing one."""
    admin, org_id = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    bob_id = (await bob.get("/api/me")).json()["id"]
    assert (await admin.patch(f"/api/org/members/{bob_id}", json={"role": "admin"})).status_code == 204
    token = token_of((await make_invite(admin))["url"])  # created by the admin who deletes their account
    carol = await sign_in(new_client(), "carol", "carol@example.org")
    admin_id = uuid.UUID((await admin.get("/api/me")).json()["id"])

    maker = app.state.sessionmaker
    async with maker() as parked, maker() as deleting_db, maker() as accepting_db:
        await parked.execute(update(User).where(User.id == admin_id).values(display_name="Leaving"))
        deleting = asyncio.create_task(delete_account(deleting_db, admin_id))
        await asyncio.sleep(0.2)  # delete_account holds the org lock and is parked on the user row
        accepting = asyncio.create_task(accept_invite(accepting_db, token, uuid.UUID(carol["id"])))
        await asyncio.sleep(0.2)  # accept_invite waits on the org lock the delete holds
        await parked.commit()  # let the delete continue...
        await asyncio.wait_for(deleting, timeout=15)
        await deleting_db.commit()  # ...which releases the org lock...
        await asyncio.wait_for(accepting, timeout=15)  # ...and the accept completes
        await accepting_db.commit()
    async with maker() as db:
        joined = await db.get(Membership, (uuid.UUID(carol["id"]), uuid.UUID(org_id)))
    assert joined is not None
