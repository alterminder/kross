"""Platform administration: creating orgs, usage reports. Superadmins only."""

from fastapi import APIRouter, Query, Request

from nlab.api.deps import Db, SuperadminDep, settings_of
from nlab.api.schemas import DayUsageOut, ModelUsageOut, NewOrgIn, NewOrgOut, OrgUsageOut, UsageOut
from nlab.db.auth_sessions import utcnow
from nlab.db.invites import new_invite
from nlab.db.models import Role
from nlab.db.orgs import create_org
from nlab.db.usage import start_of_day, usage_report, usage_since

router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_INVITE_DAYS = 14


@router.post("/orgs", status_code=201)
async def new_org(body: NewOrgIn, caller: SuperadminDep, request: Request, db: Db) -> NewOrgOut:
    """A new org and a single-use invite link that makes its first admin."""
    org = await create_org(db, body.name)
    made = await new_invite(db, org.id, Role.admin, caller.user.id, days=ADMIN_INVITE_DAYS, max_uses=1)
    await db.commit()
    return NewOrgOut(
        org_id=org.id, name=org.name, admin_invite_url=f"{settings_of(request).public_url}/invite#{made.token}"
    )


@router.get("/usage")
async def usage(caller: SuperadminDep, request: Request, db: Db, days: int = Query(7, ge=1, le=90)) -> UsageOut:
    """Model use and estimated cost: per UTC day and per model over `days` days, per org for today."""
    settings = settings_of(request)
    per_day, per_model, per_org = await usage_report(db, days, settings.model_prices)
    spent = await usage_since(db, start_of_day(utcnow()), settings.model_prices)
    return UsageOut(
        days=[DayUsageOut(**vars(row)) for row in per_day],
        models=[ModelUsageOut(**vars(row)) for row in per_model],
        orgs_today=[OrgUsageOut(**vars(row)) for row in per_org],
        ceiling_usd=settings.daily_spend_ceiling_usd,
        spent_today_usd=spent.cost_usd,
    )
