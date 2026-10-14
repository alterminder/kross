"""Sign-in with an OIDC provider, and sign-out."""

from datetime import timedelta
from typing import cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from nlab.api.deps import COOKIE, Db, settings_of
from nlab.api.identity import IdentityProvider, SignInFailed
from nlab.api.limits import limits_of
from nlab.api.schemas import GuestOptionsOut, ProviderOut
from nlab.api.storage import admit_storage
from nlab.db.accounts import new_guest, personal_org, sign_in
from nlab.db.auth_sessions import create_session, end_session, load_session
from nlab.db.models import User
from nlab.db.usage import check_guest_signups

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _providers(request: Request) -> dict[str, IdentityProvider]:
    return cast(dict[str, IdentityProvider], request.app.state.providers)


def _provider(request: Request, name: str) -> IdentityProvider:
    provider = _providers(request).get(name)
    if provider is None:
        raise HTTPException(404, "Unknown sign-in provider")
    return provider


@router.get("/providers")
async def list_providers(request: Request) -> list[ProviderOut]:
    return [ProviderOut(name=provider.name, label=provider.label) for provider in _providers(request).values()]


@router.get("/guest")
async def guest_options(request: Request) -> GuestOptionsOut:
    return GuestOptionsOut(enabled=settings_of(request).guest_play)


@router.post("/guest", status_code=204)
async def start_guest(request: Request, db: Db) -> Response:
    """An anonymous visitor starts at once: a guest user with a personal org and a short browser session. Refused
    when the deployment has not turned guest play on, or when today's quota of new guests is used up. A browser that
    already holds a live guest keeps it: repeat requests create no new account and spend no quota."""
    settings = settings_of(request)
    if not settings.guest_play:
        raise HTTPException(404, "Guest play is not enabled")
    if previous := request.cookies.get(COOKIE):
        session = await load_session(db, previous, timedelta(hours=settings.session_idle_hours))
        if session is not None and (await db.get_one(User, session.user_id)).is_guest:
            await db.commit()  # load_session may have touched the session row
            return Response(status_code=204)  # the browser already has its guest
    await check_guest_signups(db, limits_of(settings), request.client.host if request.client else None)
    user = await new_guest(db)
    home = await personal_org(db, user.id)
    await admit_storage(db, settings, user.id, home.id, 8192)
    lifetime = timedelta(hours=settings.guest_session_hours)
    if previous := request.cookies.get(COOKIE):
        await end_session(db, previous)  # as with any sign-in: one session per browser
    token = create_session(db, user.id, home.id, lifetime, identity_id=None)  # a guest pins no identity
    await db.commit()
    response = Response(status_code=204)
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/{name}/login")
async def login(name: str, request: Request) -> Response:
    callback_url = f"{settings_of(request).public_url}/api/auth/{name}/callback"
    try:
        return await _provider(request, name).login(request, callback_url)
    except SignInFailed as exc:
        raise HTTPException(400, "Sign-in failed; try again") from exc


@router.get("/{name}/callback")
async def callback(name: str, request: Request, db: Db) -> Response:
    settings = settings_of(request)
    try:
        identity = await _provider(request, name).identity(request)
    except SignInFailed as exc:
        raise HTTPException(400, "Sign-in failed; try again") from exc
    user, link = await sign_in(db, identity, settings.superadmin_policy())
    home = await personal_org(db, user.id)
    await admit_storage(db, settings, user.id, home.id, 8192)
    if previous := request.cookies.get(COOKIE):
        await end_session(db, previous)  # signing in again in the same browser ends the previous session
    token = create_session(db, user.id, home.id, timedelta(days=settings.session_max_days), identity_id=link.id)
    await db.commit()
    response = RedirectResponse(f"{settings.public_url}/", status_code=303)
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(settings.session_max_days * 86400),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, db: Db) -> Response:
    if token := request.cookies.get(COOKIE):
        await end_session(db, token)
        await db.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/")
    return response
