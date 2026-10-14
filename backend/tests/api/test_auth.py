import uuid
from datetime import timedelta
from typing import Any, cast

import pytest
from authlib.integrations.starlette_client import OAuth
from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from joserfc.errors import BadSignatureError
from sqlalchemy import select, update

from nlab.api.identity import OidcProvider, SignInFailed
from nlab.db.accounts import VerifiedIdentity
from nlab.db.auth_sessions import utcnow
from nlab.db.models import AuthSession, Identity, Org, User
from tests.api.support import SUPERADMIN, count, sign_in
from tests.api.test_limits import limit

pytestmark = pytest.mark.anyio


class StubClient:
    """Stands in for Authlib's client: returns a fixed token or raises a fixed error, hits no network."""

    def __init__(self, outcome: dict[str, Any] | Exception) -> None:
        self.outcome = outcome

    async def authorize_access_token(self, request: Request) -> dict[str, Any]:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Response:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return RedirectResponse(redirect_uri)


async def identity_of(outcome: dict[str, Any] | Exception) -> VerifiedIdentity:
    provider = OidcProvider(OAuth(), "sso", "SSO", "https://issuer.example/metadata", "id", "secret")
    provider._client = cast(Any, StubClient(outcome))
    return await provider.identity(cast(Request, None))


async def test_first_sign_in_creates_the_user_and_their_personal_space(app, new_client):
    me = await sign_in(new_client(), "alice", "Alice@Example.org", name="Alice")
    assert me["email"] == "alice@example.org" and me["display_name"] == "Alice" and not me["is_superadmin"]
    assert me["active_org"]["personal"] and me["active_org"]["role"] == "admin"
    assert [org["id"] for org in me["orgs"]] == [me["active_org"]["id"]]


async def test_signing_in_again_finds_the_same_user(app, new_client):
    first = await sign_in(new_client(), "alice", "alice@example.org")
    again = await sign_in(new_client(), "alice", "alice@example.org")
    assert again["id"] == first["id"]
    assert await count(app, User) == 1 and await count(app, Org) == 1


async def test_a_verified_email_never_links_a_second_provider(app, new_client):
    """Finding 1: a recycled or stale verified email must not attach a new provider identity to an existing
    account. Same address, two provider identities: two different users."""
    first = await sign_in(new_client(), "alice", "alice@example.org")
    other = await sign_in(new_client(), "alice-2", "alice@example.org", provider="fake2")
    assert other["id"] != first["id"] and await count(app, User) == 2


async def test_an_unverified_email_never_links(app, new_client):
    first = await sign_in(new_client(), "alice", "alice@example.org")
    impostor = await sign_in(new_client(), "mallory", "alice@example.org", verified=False, provider="fake2")
    assert impostor["id"] != first["id"]


async def test_an_unverified_account_is_never_linked_by_a_later_verified_one(app, new_client):
    mallory = await sign_in(new_client(), "mallory", "alice@example.org", verified=False)
    alice = await sign_in(new_client(), "alice", "alice@example.org", provider="fake2")
    assert alice["id"] != mallory["id"] and await count(app, User) == 2


async def test_a_new_subject_from_the_same_provider_never_links_by_email(app, new_client):
    """One provider, two subjects, one verified email: two different people, two different users."""
    old = await sign_in(new_client(), "alice-old-sub", "alice@corp.example")
    new = await sign_in(new_client(), "new-hire-sub", "alice@corp.example")
    assert new["id"] != old["id"]


async def test_linking_needs_exactly_one_candidate(app, new_client):
    """Two verified users can share one address (same provider, two subjects): a third provider's new identity
    must join neither of them and becomes a third user."""
    old = await sign_in(new_client(), "alice-old-sub", "alice@corp.example")
    new = await sign_in(new_client(), "new-hire-sub", "alice@corp.example")
    third = await sign_in(new_client(), "g-alice", "alice@corp.example", provider="fake2")
    assert third["id"] not in {old["id"], new["id"]} and await count(app, User) == 3


async def test_signing_in_refreshes_a_stale_email(app, new_client):
    client = new_client()
    await sign_in(client, "alice", "alice@gmail.example")
    me = await sign_in(client, "alice", "alice@corp.example")
    assert me["email"] == "alice@corp.example"


async def test_the_account_email_does_not_follow_the_last_provider(app, new_client):
    """Already stored identity links are preserved (the identity policy only stops creating new ones): while one exists,
    an identity may refresh the account email only as long as its own stored claim matches it."""
    first = await sign_in(new_client(), "alice", "alice@gmail.example")
    async with app.state.sessionmaker() as db:  # a link stored before email-based linking was removed
        db.add(
            Identity(
                user_id=uuid.UUID(first["id"]),
                provider="fake2",
                subject="g-alice",
                email="alice@gmail.example",
                email_verified=True,
            )
        )
        await db.commit()
    renamed = await sign_in(new_client(), "g-alice", "alice@corp.example", provider="fake2")
    assert renamed["id"] == first["id"]
    assert renamed["email"] == "alice@corp.example"  # the stored claim matched, so it renamed the account
    again = await sign_in(new_client(), "alice", "alice@gmail.example")
    assert again["id"] == first["id"] and again["email"] == "alice@corp.example"


async def test_signing_in_again_ends_the_previous_session(app, new_client):
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    old_token = client.cookies["nlab_session"]
    await sign_in(client, "alice", "alice@example.org")
    assert client.cookies["nlab_session"] != old_token
    old_browser = new_client()
    old_browser.cookies.set("nlab_session", old_token)
    assert (await old_browser.get("/api/me")).status_code == 401
    assert (await client.get("/api/me")).status_code == 200


async def test_superadmin_rights_come_from_the_configured_identity(app, new_client):
    """Finding 1: platform-admin rights bind to provider + stable subject, never to an email claim."""
    assert (await sign_in(new_client(), "root", SUPERADMIN))["is_superadmin"]  # the configured identity
    assert not (await sign_in(new_client(), "root-2", SUPERADMIN))["is_superadmin"]  # another subject
    assert not (await sign_in(new_client(), "root", SUPERADMIN, provider="fake2"))["is_superadmin"]  # other provider


async def test_the_legacy_email_allowlist_grants_nobody(app, new_client):
    """NLAB_SUPERADMIN_EMAILS is deprecated and fails closed: a verified email is not an identity."""
    limit(app, superadmin_emails=SUPERADMIN)  # an unmigrated deployment
    assert not (await sign_in(new_client(), "mail-root", SUPERADMIN))["is_superadmin"]


async def test_superadmin_rights_are_reevaluated_at_every_sign_in(app, new_client):
    root = new_client()
    assert (await sign_in(root, "root", SUPERADMIN))["is_superadmin"]
    limit(app, superadmin_identities={})  # the configured policy changed
    assert not (await sign_in(root, "root", SUPERADMIN))["is_superadmin"]


async def test_the_real_oidc_provider_parses_the_verified_claim_safely():
    def token(verified: Any) -> dict[str, Any]:
        return {"userinfo": {"sub": "s", "email": "alice@example.org", "email_verified": verified}}

    assert (await identity_of(token(True))).email_verified
    assert (await identity_of(token("true"))).email_verified
    assert not (await identity_of(token("false"))).email_verified  # the string "false" is not true
    assert not (await identity_of(token(None))).email_verified
    with pytest.raises(SignInFailed):
        await identity_of({"userinfo": {"email": "alice@example.org"}})  # no subject


async def test_an_invalid_id_token_is_a_sign_in_failure():
    """joserfc (Authlib 1.8's ID-token layer) errors subclass Exception, not AuthlibBaseError."""
    with pytest.raises(SignInFailed):
        await identity_of(BadSignatureError())  # a token signed with the wrong key


async def test_the_session_cookie_is_http_only_and_lax(app, new_client):
    client = new_client()
    login = await client.get("/api/auth/fake/login", params={"sub": "alice", "email": "a@example.org", "verified": "1"})
    callback = await client.get(login.headers["location"])
    cookie = callback.headers["set-cookie"]
    assert cookie.startswith("nlab_session=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Path=/" in cookie and callback.headers["location"] == "http://test/"


async def test_the_session_cookie_is_secure_when_configured(app, new_client):
    app.state.settings.cookie_secure = True
    client = new_client()
    login = await client.get("/api/auth/fake/login", params={"sub": "alice", "email": "a@example.org", "verified": "1"})
    callback = await client.get(login.headers["location"])
    assert "Secure" in callback.headers["set-cookie"]


async def test_the_session_token_is_stored_hashed(app, new_client):
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    async with app.state.sessionmaker() as db:
        stored = await db.scalar(select(AuthSession.id_hash))
    assert stored != client.cookies["nlab_session"] and len(stored) == 64


async def test_without_a_session_the_api_asks_to_sign_in(app, new_client):
    assert (await new_client().get("/api/me")).status_code == 401


async def test_logout_ends_the_session(app, new_client):
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/me")).status_code == 401
    assert await count(app, AuthSession) == 0


@pytest.mark.parametrize(("field", "hours"), [("last_seen_at", -9), ("expires_at", 0)])
async def test_an_idle_or_expired_session_ends(app, new_client, field, hours):
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    async with app.state.sessionmaker() as db:
        await db.execute(update(AuthSession).values({field: utcnow() + timedelta(hours=hours)}))
        await db.commit()
    assert (await client.get("/api/me")).status_code == 401
    assert await count(app, AuthSession) == 0


async def test_an_active_session_is_refreshed(app, new_client):
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    back = utcnow() - timedelta(minutes=6)  # beyond the five-minute touch interval
    async with app.state.sessionmaker() as db:
        await db.execute(update(AuthSession).values(last_seen_at=back))
        await db.commit()
    assert (await client.get("/api/me")).status_code == 200
    async with app.state.sessionmaker() as db:
        seen = await db.scalar(select(AuthSession.last_seen_at))
    assert seen is not None and seen > back


async def test_providers_are_listed_and_unknown_ones_are_404(app, new_client):
    client = new_client()
    assert {p["name"] for p in (await client.get("/api/auth/providers")).json()} == {"fake", "fake2"}
    assert (await client.get("/api/auth/nope/login")).status_code == 404
