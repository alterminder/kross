"""Durable conservative write allowances, independent of deletable application data."""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.errors import LimitReached
from nlab.db.models import StorageBucket

LIFETIME = date(1970, 1, 1)
GLOBAL = uuid.UUID(int=0)


async def admit_write(
    db: AsyncSession,
    *,
    day: date,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    charged_bytes: int,
    limits: Sequence[tuple[Literal["user", "org", "global"], int, int]],
) -> None:
    # One short transaction serializes admission; it is committed before endpoint work starts.
    await db.execute(text("SELECT pg_advisory_xact_lock(1313620290, 2)"))
    changed: list[StorageBucket] = []
    for scope, daily_limit, storage_limit in limits:
        identity = {"user": user_id, "org": org_id, "global": GLOBAL}[scope]
        for bucket_day, limit, label in (
            (day, daily_limit, "daily write"),
            (LIFETIME, storage_limit, "storage"),
        ):
            bucket = await db.get(StorageBucket, (scope, identity, bucket_day))
            if bucket is None:
                bucket = StorageBucket(scope=scope, scope_id=identity, day=bucket_day, writes=0, bytes_written=0)
                db.add(bucket)
            used = bucket.writes + 1 if bucket_day != LIFETIME else bucket.bytes_written + charged_bytes
            if used > limit:
                raise LimitReached(f"The {scope} {label} allowance is exhausted. Contact the administrator.")
            changed.append(bucket)
    for bucket in changed:
        bucket.writes += 1
        bucket.bytes_written += charged_bytes
    await db.flush()


async def purge_write_days(db: AsyncSession, before: date) -> None:
    from sqlalchemy import delete

    await db.execute(delete(StorageBucket).where(StorageBucket.day < before, StorageBucket.day != LIFETIME))
