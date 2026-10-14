import uuid

import pytest
from sqlalchemy import select

from nlab.api import auth_admin
from nlab.db.models import AuthSession
from tests.api.support import SUPERADMIN, sign_in, token_of

pytestmark = pytest.mark.anyio


async def test_a_superadmin_creates_an_org_with_a_single_use_admin_invite(app, new_client):
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    created = await root.post("/api/admin/orgs", json={"name": "Geneva Office"})
    assert created.status_code == 201
    token = token_of(created.json()["admin_invite_url"])
    dana = new_client()
    await sign_in(dana, "dana", "dana@example.org")
    assert (await dana.post("/api/invites/accept", json={"token": token, "acknowledged": True})).status_code == 200
    assert (await dana.get("/api/me")).json()["active_org"]["role"] == "admin"
    eve = new_client()
    await sign_in(eve, "eve", "eve@example.org")
    assert (await eve.post("/api/invites/accept", json={"token": token, "acknowledged": True})).status_code == 410


async def test_only_superadmins_create_orgs(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.post("/api/admin/orgs", json={"name": "Mine"})).status_code == 403


async def test_an_org_needs_a_real_name(app, new_client):
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    assert (await root.post("/api/admin/orgs", json={"name": "   "})).status_code == 422


async def test_the_operator_cli_lists_identities_without_session_tokens(app, new_client):
    """The listing shows what goes into NLAB_SUPERADMIN_IDENTITIES (user id, provider, stable subject) and can
    never leak session tokens or their hashes into an operator's terminal or logs."""
    alice = new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    report = await auth_admin.identities(app.state.settings)
    assert me["id"] in report and "fake" in report and "alice@example.org" in report
    async with app.state.sessionmaker() as db:
        stored = (await db.scalars(select(AuthSession.id_hash))).all()
    assert alice.cookies["nlab_session"] not in report
    assert all(id_hash not in report for id_hash in stored)
    assert (await alice.get("/api/me")).status_code == 200  # listing is read-only: nothing was revoked


async def test_the_operator_cli_revokes_every_session_of_one_explicit_user(app, new_client):
    """Revocation needs an explicit user id (never an implicit repair) and is immediate for every browser."""
    with pytest.raises(SystemExit):
        auth_admin.main(["revoke-sessions"])  # no --user-id: the CLI refuses to guess
    alice, in_two_browsers, bob = new_client(), new_client(), new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    await sign_in(in_two_browsers, "alice", "alice@example.org")  # a second session of the same user
    await sign_in(bob, "bob", "bob@example.org")
    assert (await alice.get("/api/me")).status_code == 200  # the refused command did nothing
    revoked = await auth_admin.revoke(app.state.settings, uuid.UUID(me["id"]))
    assert revoked == 2
    assert (await alice.get("/api/me")).status_code == 401
    assert (await in_two_browsers.get("/api/me")).status_code == 401
    assert (await bob.get("/api/me")).status_code == 200  # only the selected user
