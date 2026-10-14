"""Request dependencies: the database session, the signed-in caller, the active org and role checks.
Authorisation is checked on every request against the membership in the active org, never cached in the cookie."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nlab.api.budget import Actor, Budgeted
from nlab.api.content import Content
from nlab.api.settings import Settings
from nlab.db.accounts import superadmin_of
from nlab.db.auth_sessions import load_session
from nlab.db.models import AuthSession, User
from nlab.db.orgs import OrgContext, org_context
from nlab.db.scenarios import Viewer
from nlab.llm import LLMConfig, Provider

COOKIE = "nlab_session"

# What a guest (an anonymous visitor) may call: read the library, play a scenario alone, read the debrief and ask the
# coach. Keyed by the route's own path template, so a new endpoint is closed to guests until it is listed here.
GUEST_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/me"),
        ("GET", "/api/me/allowance"),
        ("GET", "/api/scenarios"),
        ("GET", "/api/scenarios/{scenario_id}"),
        ("GET", "/api/scenarios/{scenario_id}/cover-image"),
        ("GET", "/api/sessions"),
        ("POST", "/api/sessions"),
        ("GET", "/api/sessions/{session_id}"),
        ("PUT", "/api/sessions/{session_id}/preparation"),
        ("PUT", "/api/sessions/{session_id}/reflection"),
        ("POST", "/api/sessions/{session_id}/interlocutor"),
        ("POST", "/api/sessions/{session_id}/turns"),
        ("POST", "/api/sessions/{session_id}/nudge"),
        ("POST", "/api/sessions/{session_id}/end"),
        ("POST", "/api/sessions/{session_id}/time-up"),
        ("GET", "/api/sessions/{session_id}/debrief"),
        ("GET", "/api/sessions/{session_id}/coach/suggestions"),
        ("POST", "/api/sessions/{session_id}/coach"),
        ("GET", "/api/knowledge"),
        ("GET", "/api/knowledge/{doc_id}"),
    }
)


def settings_of(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Endpoints commit what they change; anything uncommitted is rolled back."""
    maker = cast(async_sessionmaker[AsyncSession], request.app.state.sessionmaker)
    async with maker() as db:
        yield db


Db = Annotated[AsyncSession, Depends(get_db)]


@dataclass(frozen=True)
class Caller:
    user: User
    session: AuthSession
    is_superadmin: bool  # the request-local result of the current policy on this session's identity; never stale


async def get_caller(request: Request, db: Db) -> Caller:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sign in first")
    session = await load_session(db, token, timedelta(hours=settings_of(request).session_idle_hours))
    if session is None:
        await db.commit()  # an ended session's row was deleted
        raise HTTPException(401, "Your session has ended; sign in again")
    user = await db.get_one(User, session.user_id)
    # The session's authenticated identity + the current policy decide the platform role, reconciled on every
    # request: a revoked grant denies this cookie at once, and a historical linked identity never
    # inherits another identity's grant. The column is display/cache only; every authorisation below (and /api/me)
    # reads the request-local result, so concurrent sessions cannot pick each other's cached role.
    granted = await superadmin_of(db, session.identity_id, settings_of(request).superadmin_policy())
    if user.is_superadmin != granted:
        user.is_superadmin = granted  # display cache; consumers read the request-local Caller.is_superadmin
    await db.commit()
    if user.is_guest and (request.method, getattr(request.scope.get("route"), "path", "")) not in GUEST_ALLOWED:
        raise HTTPException(403, "Sign in to use this")
    return Caller(user=user, session=session, is_superadmin=granted)


CallerDep = Annotated[Caller, Depends(get_caller)]


async def get_org(caller: CallerDep, db: Db) -> OrgContext:
    context = await org_context(db, caller.session)
    await db.commit()
    return context


OrgDep = Annotated[OrgContext, Depends(get_org)]


async def require_admin(context: OrgDep) -> OrgContext:
    if not context.is_admin:
        raise HTTPException(403, "Only an admin of this org can do that")
    return context


AdminDep = Annotated[OrgContext, Depends(require_admin)]


async def require_superadmin(caller: CallerDep) -> Caller:
    if not caller.is_superadmin:
        raise HTTPException(403, "Only a platform superadmin can do that")
    return caller


SuperadminDep = Annotated[Caller, Depends(require_superadmin)]


async def get_viewer(caller: CallerDep, context: OrgDep) -> Viewer:
    return Viewer(context=context, is_superadmin=caller.is_superadmin)


ViewerDep = Annotated[Viewer, Depends(get_viewer)]


def content_of(request: Request) -> Content:
    return cast(Content, request.app.state.content)


def llm_of(request: Request) -> tuple[Provider, LLMConfig]:
    """The model provider and settings; 503 when this server has no model configured."""
    provider, config = request.app.state.llm
    if config is None:
        raise HTTPException(503, "No language model is configured on this server")
    return cast(Provider, provider), cast(LLMConfig, config)


def budgeted_llm_of(request: Request, actor: "Actor") -> tuple[Provider, LLMConfig]:
    """The model provider wrapped in the shared budget guard for `actor` (the checked caller for interactive work,
    the session's owner for background work): every billed call reserves its bounded worst case before it runs."""
    provider, config = llm_of(request)
    return (
        Budgeted(provider, request.app.state.sessionmaker, actor, lambda: settings_of(request)),
        config,
    )
