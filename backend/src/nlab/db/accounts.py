"""Accounts: sign-in with a verified identity, the personal org every user gets, and account deletion."""

import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.errors import Conflict
from nlab.db.models import Identity, Membership, Org, Role, Scenario, User, Visibility


@dataclass(frozen=True)
class VerifiedIdentity:
    """What an identity provider vouches for after a successful sign-in."""

    provider: str
    subject: str
    email: str | None
    email_verified: bool
    name: str | None


def is_superadmin(provider: str, subject: str, policy: Mapping[str, Collection[str]]) -> bool:
    """Platform-admin rights bind to a configured provider and its stable subject, never to an email claim
    (reassigned mailboxes and stale claims identify different people)."""
    return subject in policy.get(provider, ())


async def superadmin_of(db: AsyncSession, identity_id: uuid.UUID | None, policy: Mapping[str, Collection[str]]) -> bool:
    """Platform-admin rights follow the identity that authenticated the session and the current provider+subject
    policy - never any identity on the account: a historical implicit link must not inherit another identity's
    grant. A session without a pinned identity (guests, pre-migration sessions) fails admin closed. The policy is
    the source of truth; User.is_superadmin is only a display cache."""
    if identity_id is None or not policy:
        return False
    link = await db.get(Identity, identity_id)
    return link is not None and is_superadmin(link.provider, link.subject, policy)


async def sign_in(
    db: AsyncSession, identity: VerifiedIdentity, superadmin_policy: Mapping[str, Collection[str]]
) -> tuple[User, Identity]:
    """The user behind an identity, created with a personal org on first sign-in, and the identity row that
    authenticated them (the caller pins the new session to it). An identity is provider + subject and nothing
    else: a new identity becomes its own user even when a verified email matches an existing account,
    because a recycled mailbox or a stale third-party claim must never hand one person another person's account.
    Already stored links keep working."""
    email = identity.email.strip().lower() if identity.email else None
    verified = bool(email) and identity.email_verified
    link = await db.scalar(
        select(Identity).where(Identity.provider == identity.provider, Identity.subject == identity.subject)
    )
    if link is not None:
        user = await db.get_one(User, link.user_id)
        if verified and link.email == user.email:
            # only the identity whose claim the account email came from may refresh it, or the account email
            # would follow whichever provider signed in last
            user.email, user.email_verified = email, True
        link.email, link.email_verified = email, identity.email_verified  # refresh stale claims
    else:
        user = await _new_user(db, email, verified, identity.name)
        link = Identity(
            user_id=user.id,
            provider=identity.provider,
            subject=identity.subject,
            email=email,
            email_verified=identity.email_verified,
        )
        db.add(link)
    await db.flush()
    user.is_superadmin = is_superadmin(identity.provider, identity.subject, superadmin_policy)  # display cache
    return user, link


async def _new_user(db: AsyncSession, email: str | None, verified: bool, name: str | None) -> User:
    display = (name or (email or "").split("@")[0] or "New user")[:200]
    user = User(email=email, email_verified=verified, display_name=display)
    db.add(user)
    await db.flush()
    org = Org(name="Personal", personal_owner_id=user.id)
    db.add(org)
    await db.flush()
    db.add(Membership(user_id=user.id, org_id=org.id, role=Role.admin))
    return user


async def new_guest(db: AsyncSession) -> User:
    """An anonymous visitor: a user with no email and no identity, and a personal org like everyone's."""
    user = await _new_user(db, None, False, "Guest")
    user.is_guest = True
    await db.flush()
    return user


async def purge_guests(db: AsyncSession, before: datetime) -> int:
    """Deletes guests created before `before` (their sessions and org go with them). Callers pass the start of
    yesterday: a guest's browser session lasts a day at most, and the daily caps read only today's usage."""
    gone = await db.scalars(delete(User).where(User.is_guest.is_(True), User.created_at < before).returning(User.id))
    return len(gone.all())


async def personal_org(db: AsyncSession, user_id: uuid.UUID) -> Org:
    return (await db.scalars(select(Org).where(Org.personal_owner_id == user_id))).one()


async def delete_account(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Deletes the user; the database cascades identities, sessions, memberships and the personal org. An org where
    the user is the only member goes with the account (everything in it was theirs). Refused while the user is the
    only admin of an org with other members."""
    await db.execute(  # lock the orgs where this user is admin, always in id order: FOR NO KEY UPDATE serialises
        # the admin checks without blocking the foreign-key checks of membership inserts (invite acceptance),
        # and the fixed order keeps two concurrent deletions from locking shared orgs in opposite orders
        select(Org.id)
        .join(Membership, Membership.org_id == Org.id)
        .where(Membership.user_id == user_id, Membership.role == Role.admin)
        .order_by(Org.id)
        .with_for_update(key_share=True)
    )
    # accept_invite holds the same lock on the org row before it adds its membership, so a concurrent accept either
    # committed first (the count below sees the new member) or still waits and finds the org gone: an accepted
    # invite is never counted away silently
    only_member = select(Membership.org_id).group_by(Membership.org_id).having(func.count() == 1)
    await db.execute(
        delete(Org).where(
            Org.personal_owner_id.is_(None),  # the personal org cascades with the user row
            Org.is_system.is_(False),
            Org.id.in_(only_member),
            Org.id.in_(select(Membership.org_id).where(Membership.user_id == user_id)),
        )
    )
    single_admin_orgs = (
        select(Membership.org_id)
        .where(Membership.role == Role.admin)
        .group_by(Membership.org_id)
        .having(func.count() == 1)
    )
    blocking = await db.scalar(
        select(Org.name)
        .join(Membership, Membership.org_id == Org.id)
        .where(
            Membership.user_id == user_id,
            Membership.role == Role.admin,
            Org.personal_owner_id.is_(None),
            Org.id.in_(single_admin_orgs),
        )
        .limit(1)
    )
    if blocking is not None:
        raise Conflict(f"You are the only admin of {blocking}. Make someone else admin first.")
    # by design: deleting an account deletes the user's private scenarios, in every org (only the personal org's
    # would cascade away with the org itself); versions go with them. Org and public scenarios stay.
    await db.execute(delete(Scenario).where(Scenario.owner_id == user_id, Scenario.visibility == Visibility.private))
    await db.execute(delete(User).where(User.id == user_id))
