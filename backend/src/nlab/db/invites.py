"""Invite links: a random token, stored hashed, that lets a signed-in user join an org. No email is sent."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.auth_sessions import hash_token, utcnow
from nlab.db.errors import Conflict, Gone, NotFound
from nlab.db.models import Invite, Membership, Org, Role
from nlab.db.orgs import OrgContext, membership

INVITE_NOTICE = (
    "Admins of {org} can see and steer your practice sessions in this org, including while you play (they can "
    "adjust the counterpart and add twists), comment on them, and read your debriefs."
)
PROBLEMS = {
    "revoked": "This invite was revoked",
    "expired": "This invite has expired",
    "used_up": "This invite has been used up",
}


@dataclass(frozen=True)
class NewInvite:
    invite: Invite
    token: str  # shown once, in the response that creates the invite


@dataclass(frozen=True)
class InviteView:
    invite: Invite
    org: Org
    problem: str | None
    already_member: bool


async def new_invite(
    db: AsyncSession, org_id: uuid.UUID, role: Role, created_by: uuid.UUID, days: int, max_uses: int
) -> NewInvite:
    token = secrets.token_urlsafe(24)
    invite = Invite(
        org_id=org_id,
        token_hash=hash_token(token),
        role=role,
        created_by=created_by,
        expires_at=utcnow() + timedelta(days=days),
        max_uses=max_uses,
    )
    db.add(invite)
    await db.flush()
    return NewInvite(invite=invite, token=token)


async def create_invite(db: AsyncSession, context: OrgContext, days: int, max_uses: int) -> NewInvite:
    """An org admin's invite link; it grants the member role."""
    if context.is_personal:
        raise Conflict("A personal space cannot have other members")
    return await new_invite(db, context.org_id, Role.member, context.user_id, days, max_uses)


async def list_invites(db: AsyncSession, context: OrgContext) -> list[Invite]:
    """The org's invites that can still be used."""
    now = utcnow()
    return list(
        await db.scalars(
            select(Invite)
            .where(
                Invite.org_id == context.org_id,
                Invite.revoked_at.is_(None),
                Invite.expires_at > now,
                Invite.uses < Invite.max_uses,
            )
            .order_by(Invite.created_at)
        )
    )


async def revoke_invite(db: AsyncSession, context: OrgContext, invite_id: uuid.UUID) -> None:
    invite = await db.scalar(select(Invite).where(Invite.id == invite_id, Invite.org_id == context.org_id))
    if invite is None:
        raise NotFound("No such invite")
    invite.revoked_at = invite.revoked_at or utcnow()


def _problem(invite: Invite) -> str | None:
    if invite.revoked_at is not None:
        return "revoked"
    if invite.expires_at <= utcnow():
        return "expired"
    if invite.uses >= invite.max_uses:
        return "used_up"
    return None


async def view_invite(db: AsyncSession, token: str, user_id: uuid.UUID) -> InviteView:
    row = (
        await db.execute(
            select(Invite, Org).join(Org, Org.id == Invite.org_id).where(Invite.token_hash == hash_token(token))
        )
    ).first()
    if row is None:
        raise NotFound("This invite link is not valid")
    invite, org = row
    already = await membership(db, user_id, org.id) is not None
    return InviteView(invite=invite, org=org, problem=_problem(invite), already_member=already)


async def accept_invite(db: AsyncSession, token: str, user_id: uuid.UUID) -> Org:
    """Joins the invite's org with the invite's role. Accepting again as a member changes and uses nothing."""
    view = await view_invite(db, token, user_id)
    if view.already_member:
        return view.org
    if view.problem is not None:
        raise Gone(PROBLEMS[view.problem])
    # Lock the org row (FOR NO KEY UPDATE, the mode delete_account takes) before touching the invite, and hold it
    # to commit: a sole-member org deletion then either already removed the org (refuse here) or waits for this
    # accept and re-counts two members. Lock order stays org before invite, as in delete_account.
    locked = await db.scalar(select(Org.id).where(Org.id == view.org.id).with_for_update(key_share=True))
    if locked is None:
        raise NotFound("This invite link is not valid")
    taken = await db.scalar(  # atomic: two people cannot take the last place
        update(Invite)
        .where(
            Invite.id == view.invite.id,
            Invite.revoked_at.is_(None),
            Invite.expires_at > utcnow(),
            Invite.uses < Invite.max_uses,
        )
        .values(uses=Invite.uses + 1)
        .returning(Invite.id)
    )
    if taken is None:
        raise Gone(PROBLEMS["used_up"])
    db.add(Membership(user_id=user_id, org_id=view.org.id, role=view.invite.role))
    await db.flush()
    return view.org
