"""Managing the active org: members, roles and invite links. Admins only."""

import uuid

from fastapi import APIRouter, Request

from nlab.api.deps import AdminDep, Db, settings_of
from nlab.api.schemas import InviteIn, InviteOut, MemberOut, RoleIn
from nlab.db.invites import create_invite, list_invites, revoke_invite
from nlab.db.models import Invite
from nlab.db.orgs import members, remove_member, set_role

router = APIRouter(prefix="/api/org", tags=["org"])


def invite_out(invite: Invite, url: str | None = None) -> InviteOut:
    return InviteOut(
        id=invite.id,
        role=invite.role,
        expires_at=invite.expires_at,
        max_uses=invite.max_uses,
        uses=invite.uses,
        url=url,
    )


@router.get("/members")
async def list_members(context: AdminDep, db: Db) -> list[MemberOut]:
    return [
        MemberOut(user_id=user.id, display_name=user.display_name, email=user.email, role=role)
        for user, role in await members(db, context)
    ]


@router.patch("/members/{user_id}", status_code=204)
async def change_role(user_id: uuid.UUID, body: RoleIn, context: AdminDep, db: Db) -> None:
    await set_role(db, context, user_id, body.role)
    await db.commit()


@router.delete("/members/{user_id}", status_code=204)
async def remove(user_id: uuid.UUID, context: AdminDep, db: Db) -> None:
    await remove_member(db, context, user_id)
    await db.commit()


@router.post("/invites", status_code=201)
async def invite(body: InviteIn, context: AdminDep, request: Request, db: Db) -> InviteOut:
    made = await create_invite(db, context, body.days, body.max_uses)
    await db.commit()
    return invite_out(made.invite, f"{settings_of(request).public_url}/invite#{made.token}")


@router.get("/invites")
async def invites(context: AdminDep, db: Db) -> list[InviteOut]:
    return [invite_out(item) for item in await list_invites(db, context)]


@router.delete("/invites/{invite_id}", status_code=204)
async def revoke(invite_id: uuid.UUID, context: AdminDep, db: Db) -> None:
    await revoke_invite(db, context, invite_id)
    await db.commit()
