"""Orgs and memberships. Every function that reads or changes an org's data takes an OrgContext and filters by it."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.accounts import personal_org
from nlab.db.errors import Conflict, NotFound
from nlab.db.models import AuthSession, Membership, Org, Role, User


@dataclass(frozen=True)
class OrgContext:
    """The org a request acts in, and the caller's role there."""

    user_id: uuid.UUID
    org_id: uuid.UUID
    role: Role
    is_personal: bool
    is_guest: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == Role.admin


async def membership(db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID) -> Membership | None:
    return await db.get(Membership, (user_id, org_id))


async def context_for(db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID) -> OrgContext | None:
    row = (
        await db.execute(
            select(Membership.role, Org.personal_owner_id, User.is_guest)
            .join(Org, Org.id == Membership.org_id)
            .join(User, User.id == Membership.user_id)
            .where(Membership.user_id == user_id, Membership.org_id == org_id)
        )
    ).first()
    if row is None:
        return None
    role, owner, guest = row
    return OrgContext(user_id=user_id, org_id=org_id, role=role, is_personal=owner is not None, is_guest=guest)


async def org_context(db: AsyncSession, session: AuthSession) -> OrgContext:
    """The session's active org while the user is still a member of it; otherwise their personal org, which becomes
    the session's active org."""
    if session.active_org_id is not None:
        found = await context_for(db, session.user_id, session.active_org_id)
        if found is not None:
            return found
    home = await personal_org(db, session.user_id)
    session.active_org_id = home.id
    found = await context_for(db, session.user_id, home.id)
    if found is None:
        raise RuntimeError("A user without a personal-org membership")
    return found


async def my_orgs(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[Org, Role]]:
    """The user's orgs with their role, personal org first."""
    rows = await db.execute(
        select(Org, Membership.role)
        .join(Membership, Membership.org_id == Org.id)
        .where(Membership.user_id == user_id)
        .order_by(Org.personal_owner_id.is_(None), Org.name)
    )
    return [(org, role) for org, role in rows]


async def members(db: AsyncSession, context: OrgContext) -> list[tuple[User, Role]]:
    rows = await db.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == context.org_id)
        .order_by(User.display_name)
    )
    return [(user, role) for user, role in rows]


async def _admin_count(db: AsyncSession, org_id: uuid.UUID) -> int:
    """Locks the org row first so that two concurrent last-admin changes serialise here: the second transaction
    waits, re-counts after the first commits and is refused instead of both succeeding. FOR NO KEY UPDATE: it does
    not block the foreign-key checks that accepting an invite makes on the org row, so nothing deadlocks."""
    await db.execute(select(Org.id).where(Org.id == org_id).with_for_update(key_share=True))
    counted = await db.scalar(
        select(func.count()).select_from(Membership).where(Membership.org_id == org_id, Membership.role == Role.admin)
    )
    return int(counted or 0)


async def _member(db: AsyncSession, context: OrgContext, user_id: uuid.UUID) -> Membership:
    found = await membership(db, user_id, context.org_id)
    if found is None:
        raise NotFound("No such member")
    return found


async def set_role(db: AsyncSession, context: OrgContext, user_id: uuid.UUID, role: Role) -> None:
    if context.is_personal:
        raise Conflict("Roles cannot change in a personal space")
    admins = await _admin_count(db, context.org_id)  # locks the org row before the membership is read
    target = await _member(db, context, user_id)
    if target.role == Role.admin and role != Role.admin and admins == 1:
        raise Conflict("An org needs at least one admin")
    target.role = role


async def remove_member(db: AsyncSession, context: OrgContext, user_id: uuid.UUID) -> None:
    """Their access ends at once; their sessions that were acting in this org fall back to their personal org."""
    if context.is_personal:
        raise Conflict("Nobody can leave a personal space")
    admins = await _admin_count(db, context.org_id)  # locks the org row before the membership is read
    target = await _member(db, context, user_id)
    if target.role == Role.admin and admins == 1:
        raise Conflict("An org needs at least one admin")
    await db.delete(target)  # their sessions fall back to their personal org on the next request


async def create_org(db: AsyncSession, name: str) -> Org:
    org = Org(name=name.strip())
    db.add(org)
    await db.flush()
    return org


async def ensure_system_org(db: AsyncSession) -> Org:
    """The org that holds the curated public scenarios; created on first use."""
    org = await db.scalar(select(Org).where(Org.is_system.is_(True)))
    if org is None:
        org = Org(name="KROSS", is_system=True)
        db.add(org)
        await db.flush()
    return org
