"""Deletes old play sessions, guests, expired sign-in sessions and obsolete daily write counters:
`python -m nlab.api.purge` (for example daily from cron or a scheduled container). With the default 0, no play session
is deleted; the guest clean-up always runs, because a guest's day is over once it is yesterday."""

import asyncio
from datetime import timedelta

from sqlalchemy import delete, or_

from nlab.api.settings import Settings
from nlab.db.accounts import purge_guests
from nlab.db.auth_sessions import utcnow
from nlab.db.engine import make_engine, make_sessionmaker
from nlab.db.models import AuthSession
from nlab.db.sessions import purge_sessions
from nlab.db.storage import purge_write_days
from nlab.db.usage import purge_admissions, start_of_day


async def purge(settings: Settings) -> tuple[int, int]:
    """(play sessions deleted, guests deleted)."""
    engine = make_engine(settings.resolved_database_url())
    try:
        async with make_sessionmaker(engine)() as db:
            sessions = (
                await purge_sessions(db, settings.session_retention_days) if settings.session_retention_days > 0 else 0
            )
            guests = await purge_guests(db, start_of_day(utcnow()) - timedelta(days=1))
            now = utcnow()
            await db.execute(
                delete(AuthSession).where(
                    or_(
                        AuthSession.expires_at <= now,
                        AuthSession.last_seen_at <= now - timedelta(hours=settings.session_idle_hours),
                    )
                )
            )
            await purge_write_days(db, now.date() - timedelta(days=2))
            await purge_admissions(db)
            await db.commit()
            return sessions, guests
    finally:
        await engine.dispose()


def main() -> None:
    settings = Settings()
    sessions, guests = asyncio.run(purge(settings))
    if settings.session_retention_days > 0:
        print(f"Deleted {sessions} sessions older than {settings.session_retention_days} days")
    else:
        print("Retention is off (NLAB_SESSION_RETENTION_DAYS=0): no play session deleted")
    print(f"Deleted {guests} guests from before yesterday")
    print("Removed expired sign-in sessions and obsolete daily write counters")


if __name__ == "__main__":
    main()
