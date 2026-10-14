"""Opening and accepting an invite link. Sign-in required; the admin-visibility notice comes before joining.
The token travels in the request body and the link carries it in a URL fragment, never in the path: URLs and
Referer headers end up in logs, and the token is a bearer credential."""

from fastapi import APIRouter

from nlab.api.deps import CallerDep, Db
from nlab.api.schemas import AcceptIn, AcceptOut, InvitePreview, TokenIn
from nlab.db.invites import INVITE_NOTICE, accept_invite, view_invite

router = APIRouter(prefix="/api/invites", tags=["invites"])


@router.post("/preview")
async def preview(body: TokenIn, caller: CallerDep, db: Db) -> InvitePreview:
    view = await view_invite(db, body.token, caller.user.id)
    return InvitePreview(
        org_name=view.org.name,
        role=view.invite.role,
        notice=INVITE_NOTICE.format(org=view.org.name),
        problem=view.problem,
        already_member=view.already_member,
    )


@router.post("/accept")
async def accept(body: AcceptIn, caller: CallerDep, db: Db) -> AcceptOut:
    """`acknowledged` must be true — the user has read the admin-visibility notice — or FastAPI answers 422."""
    org = await accept_invite(db, body.token, caller.user.id)
    caller.session.active_org_id = org.id
    await db.commit()
    return AcceptOut(org_id=org.id, org_name=org.name)
