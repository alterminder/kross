"""Server-side sign-in sessions: the cookie holds a random token, the database only its SHA-256 hash."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.models import AuthSession

TOUCH_EVERY = timedelta(minutes=5)  # last_seen_at is refreshed at most this often, not on every request


def utcnow() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: AsyncSession, user_id: uuid.UUID, active_org_id: uuid.UUID, lifetime: timedelta, identity_id: uuid.UUID | None
) -> str:
    """Adds a session and returns the token for the cookie. The token itself is never stored. `identity_id` pins
    the session to the identity that authenticated it (None for guests): admin rights are resolved from it."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        AuthSession(
            id_hash=hash_token(token),
            user_id=user_id,
            identity_id=identity_id,
            active_org_id=active_org_id,
            last_seen_at=now,
            expires_at=now + lifetime,
        )
    )
    return token


async def load_session(db: AsyncSession, token: str, idle: timedelta) -> AuthSession | None:
    """The live session for a token. An expired or idle one is deleted and treated as absent."""
    session = await db.get(AuthSession, hash_token(token))
    if session is None:
        return None
    now = utcnow()
    if session.expires_at <= now or session.last_seen_at + idle <= now:
        await db.delete(session)
        return None
    if now - session.last_seen_at >= TOUCH_EVERY:
        session.last_seen_at = now
    return session


async def end_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.id_hash == hash_token(token)))


async def revoke_sessions(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Ends every session of one user at once, on every browser: the operator's containment action for a
    compromised account. Returns how many live sessions ended."""
    gone = await db.execute(delete(AuthSession).where(AuthSession.user_id == user_id).returning(AuthSession.id_hash))
    return len(gone.all())
