"""Operator actions for sign-in identities. Run where the app can reach the database:

    uv run python -m nlab.api.auth_admin identities
        # one line per sign-in identity: user id, email, provider, stable subject (for NLAB_SUPERADMIN_IDENTITIES)
    uv run python -m nlab.api.auth_admin revoke-sessions --user-id <uuid>
        # end every session of exactly that user, on every browser

Listing never changes anything; revocation is the only destructive action and it needs an explicit user id."""

import argparse
import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.api.settings import Settings
from nlab.db.auth_sessions import revoke_sessions
from nlab.db.engine import make_engine, make_sessionmaker
from nlab.db.models import Identity, User


@asynccontextmanager
async def _sessions(settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = make_engine(settings.resolved_database_url())
    try:
        async with make_sessionmaker(engine)() as db:
            yield db
    finally:
        await engine.dispose()


async def identities(settings: Settings) -> str:
    """The listing an operator sees. Session tokens and their hashes are never read here, so they can never leak
    into the terminal, the shell history or a log."""
    async with _sessions(settings) as db:
        rows = (
            await db.execute(
                select(User.id, User.email, Identity.provider, Identity.subject)
                .join(Identity, Identity.user_id == User.id)
                .order_by(User.created_at, Identity.created_at)
            )
        ).all()
    return "\n".join(f"{user_id}  {email or '-'}  {provider}  {subject}" for user_id, email, provider, subject in rows)


async def revoke(settings: Settings, user_id: uuid.UUID) -> int:
    """Ends every session of one explicitly selected user (containment for a compromised account), returning how many
    ended. Nothing else is changed: no identity, role or account is repaired behind the operator's back."""
    async with _sessions(settings) as db:
        gone = await revoke_sessions(db, user_id)
        await db.commit()
        return gone


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m nlab.api.auth_admin", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("identities", help="list users and their sign-in identities (provider and subject)")
    revoking = commands.add_parser("revoke-sessions", help="end every session of one user")
    revoking.add_argument("--user-id", required=True, type=uuid.UUID, help="the user whose sessions end")
    args = parser.parse_args(argv)
    settings = Settings()
    if args.command == "identities":
        print(asyncio.run(identities(settings)))
    else:
        print(f"Revoked {asyncio.run(revoke(settings, args.user_id))} sessions of user {args.user_id}")


if __name__ == "__main__":
    main()
