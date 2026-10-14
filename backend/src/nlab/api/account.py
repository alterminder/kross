"""The signed-in user: who they are, their orgs, the active org, the daily allowance, and account deletion."""

from datetime import timedelta

from fastapi import APIRouter, Request
from fastapi.responses import Response

from nlab.api.deps import COOKIE, CallerDep, Db, OrgDep, settings_of
from nlab.api.limits import limits_of
from nlab.api.schemas import ActiveOrgIn, AllowanceOut, MeOut, NewOrgIn, OrgOut
from nlab.db.accounts import delete_account
from nlab.db.auth_sessions import utcnow
from nlab.db.errors import NotFound
from nlab.db.models import Membership, Org, Role
from nlab.db.orgs import create_org, membership, my_orgs
from nlab.db.usage import start_of_day, usage_since

router = APIRouter(prefix="/api", tags=["account"])


def org_out(org: Org, role: Role) -> OrgOut:
    return OrgOut(id=org.id, name=org.name, role=role, personal=org.personal_owner_id is not None)


@router.get("/me")
async def me(caller: CallerDep, context: OrgDep, db: Db) -> MeOut:
    orgs = [org_out(org, role) for org, role in await my_orgs(db, caller.user.id)]
    active = next(org for org in orgs if org.id == context.org_id)
    user = caller.user
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_superadmin=caller.is_superadmin,
        is_guest=user.is_guest,
        active_org=active,
        orgs=orgs,
    )


@router.get("/me/allowance")
async def allowance(request: Request, caller: CallerDep, db: Db) -> AllowanceOut:
    """The caller's personal token allowance for the current UTC day, read from the usage ledger. A guest is
    enforced against both the general user and the guest token cap and gets the smallest enabled one as its
    reported cap (both off = unlimited); a registered user gets the user cap (0 = unlimited). Personal only: the
    org's daily cap, the deployment's budget and the guests' shared budget apply independently and can refuse a
    call even while this allowance is unused."""
    limits = limits_of(settings_of(request))
    enabled = [limits.user_tokens_per_day]
    if caller.user.is_guest:  # a guest is held to the general cap too (nlab.db.usage): report the smaller enabled one
        enabled.append(limits.guest_tokens_per_day)
    limit = min((cap for cap in enabled if cap), default=0)
    today = start_of_day(utcnow())
    used = (await usage_since(db, today, limits.prices, user_id=caller.user.id)).tokens
    resets_at = today + timedelta(days=1)
    if not limit:  # 0 switches the personal limit off: unlimited
        return AllowanceOut(used_tokens=used, limit_tokens=None, remaining_percent=None, resets_at=resets_at)
    remaining = max(0.0, min(100.0, 100.0 * (limit - used) / limit))
    return AllowanceOut(used_tokens=used, limit_tokens=limit, remaining_percent=remaining, resets_at=resets_at)


@router.post("/orgs", status_code=201)
async def start_org(body: NewOrgIn, caller: CallerDep, db: Db) -> OrgOut:
    """Any signed-in user starts an org, becomes its admin (its trainer), and lands in it."""
    org = await create_org(db, body.name)
    db.add(Membership(user_id=caller.user.id, org_id=org.id, role=Role.admin))
    caller.session.active_org_id = org.id
    await db.commit()
    return org_out(org, Role.admin)


@router.post("/orgs/active", status_code=204)
async def choose_org(body: ActiveOrgIn, caller: CallerDep, db: Db) -> None:
    if await membership(db, caller.user.id, body.org_id) is None:
        raise NotFound("You are not a member of that org")
    caller.session.active_org_id = body.org_id
    await db.commit()


@router.delete("/me", status_code=204)
async def delete_me(caller: CallerDep, db: Db) -> Response:
    await delete_account(db, caller.user.id)
    await db.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/")
    return response
