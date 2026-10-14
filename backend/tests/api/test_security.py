import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from nlab.db.models import AuthSession, Identity
from tests.api.support import SUPERADMIN, draft, org_with_admin, sign_in
from tests.api.test_limits import limit

pytestmark = pytest.mark.anyio

# Written out on purpose: reading app.UNSAFE_METHODS here would shrink this test together with the constant
# and leave a shrunken CSRF check untested.
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


async def test_a_state_changing_request_needs_the_csrf_header(app, new_client):
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    assert (await client.post("/api/auth/logout", headers={"X-Requested-With": ""})).status_code == 403
    assert (await client.get("/api/me")).status_code == 200  # the refused logout did nothing


async def test_every_unsafe_route_needs_the_csrf_header(app, new_client):
    """A sweep over the API surface: no POST/PUT/PATCH/DELETE may slip past the check, whatever its path."""
    open_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")  # no X-Requested-With
    checked = 0
    for path, operations in app.openapi()["paths"].items():
        for method in sorted({m for m in UNSAFE if m.lower() in operations}):
            url = re.sub(r"\{[^}]+\}", "x", path)
            assert (await open_client.request(method, url)).status_code == 403, f"{method} {url}"
            checked += 1
    await open_client.aclose()
    assert checked > 0


async def test_the_csrf_header_is_required_under_a_root_path(app, new_client):
    """Mounted behind a reverse proxy on a sub-path (--root-path /nlab) the check must not switch off."""
    admin, _ = await org_with_admin(new_client)
    sub = AsyncClient(transport=ASGITransport(app=app, root_path="/nlab"), base_url="http://test")
    sub.cookies.set("nlab_session", admin.cookies["nlab_session"])
    assert (await sub.post("/nlab/api/org/invites", json={})).status_code == 403
    made = await sub.post("/nlab/api/org/invites", json={}, headers={"X-Requested-With": "nlab"})
    assert made.status_code == 201, made.text
    await sub.aclose()


async def test_health(app, new_client):
    assert (await new_client().get("/api/health")).json() == {"ok": True}


async def test_a_revoked_grant_denies_the_previous_cookie_at_once(app, new_client):
    """Finding 9: the configured provider+subject policy is rechecked on every authenticated request, so removing
    a grant is immediate containment. The role does not survive in the cookie and does not leak through /api/me."""
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    assert (await root.get("/api/admin/usage")).status_code == 200
    limit(app, superadmin_identities={})  # the operator removed the grant
    assert (await root.get("/api/admin/usage")).status_code == 403
    assert not (await root.get("/api/me")).json()["is_superadmin"]


async def test_a_revoked_superadmin_keeps_no_scenario_powers(app, new_client):
    """The scenario Viewer reads the same reconciled role: no stale superadmin scope leaks into publishing."""
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    made = (await root.post("/api/scenarios", json={"content": draft("Curated one")})).json()
    assert (
        await root.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "public"})
    ).status_code == 204
    limit(app, superadmin_identities={})  # the operator removed the grant
    second = (await root.post("/api/scenarios", json={"content": draft("Another one")})).json()
    refused = await root.post(f"/api/scenarios/{second['id']}/visibility", json={"visibility": "public"})
    assert refused.status_code == 403


async def test_a_linked_identity_never_inherits_the_grant_of_another(app, new_client):
    """The role follows the identity that authenticated the session and the current policy, never any identity on
    the account: a historical implicit link must not hand one person the grant of another identity."""
    root = new_client()
    me = await sign_in(root, "root", SUPERADMIN)  # the allowlisted identity
    async with app.state.sessionmaker() as db:  # a link stored before email-based linking was removed
        db.add(
            Identity(
                user_id=uuid.UUID(me["id"]),
                provider="fake2",
                subject="g-root",
                email=SUPERADMIN,
                email_verified=True,
            )
        )
        await db.commit()
    other = new_client()
    await sign_in(other, "g-root", SUPERADMIN, provider="fake2")  # the same account, an unlisted identity
    assert (await other.get("/api/admin/usage")).status_code == 403
    assert not (await other.get("/api/me")).json()["is_superadmin"]
    assert (await root.get("/api/admin/usage")).status_code == 200  # the allowlisted session keeps its grant


async def test_a_session_without_an_authenticated_identity_fails_admin_closed(app, new_client):
    """Guests and pre-migration sessions pin no identity: they can never be admins, whatever the account holds."""
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    async with app.state.sessionmaker() as db:  # a pre-migration session row
        await db.execute(update(AuthSession).values(identity_id=None))
        await db.commit()
    assert (await root.get("/api/admin/usage")).status_code == 403
    assert not (await root.get("/api/me")).json()["is_superadmin"]
