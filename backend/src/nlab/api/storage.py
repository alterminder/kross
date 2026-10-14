"""Global admission for authenticated writes, including endpoints added in the future."""

import uuid
from datetime import timedelta

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.api.deps import COOKIE, Db, settings_of
from nlab.api.settings import Settings
from nlab.db.auth_sessions import load_session, utcnow
from nlab.db.orgs import org_context
from nlab.db.storage import admit_write

STATELESS = {
    "/api/scenarios/validate",
    "/api/scenarios/builder",
    "/api/scenarios/builder/picture",
    "/api/scenarios/convert",
}


async def write_limit(request: Request, db: Db) -> None:
    if request.method not in {"POST", "PUT", "PATCH"}:
        return  # deletion stays available even when allowance has been exhausted
    path = getattr(request.scope.get("route"), "path", "")
    if (
        path.startswith("/api/auth/")
        or path in STATELESS
        or path.endswith(("/coach", "/end", "/time-up", "/time-decision"))
    ):
        return  # identity and paid-call admission have their own limits
    token = request.cookies.get(COOKIE)
    if not token:
        return  # the route's own authentication produces the normal 401
    settings = settings_of(request)
    session = await load_session(db, token, timedelta(hours=settings.session_idle_hours))
    if session is None:
        await db.commit()
        return
    context = await org_context(db, session)
    size = max(1024, getattr(request.state, "body_bytes", 0))
    if path.startswith("/api/scenarios") or path == "/api/rules":
        size = max(size, 2_000_000)  # a version plus a copied cover, including JSONB overhead
    elif path.startswith("/api/sessions"):
        size = max(size, 1_000_000)  # engine snapshots, request trace and bounded model output
    await admit_storage(db, settings, context.user_id, context.org_id, size)
    await db.commit()


async def admit_storage(
    db: AsyncSession,
    settings: Settings,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    size: int,
) -> None:
    await admit_write(
        db,
        day=utcnow().date(),
        user_id=user_id,
        org_id=org_id,
        charged_bytes=size,
        limits=[
            ("user", settings.limit_user_writes_per_day, settings.limit_user_storage_bytes),
            ("org", settings.limit_org_writes_per_day, settings.limit_org_storage_bytes),
            ("global", settings.limit_total_writes_per_day, settings.limit_total_storage_bytes),
        ],
    )
