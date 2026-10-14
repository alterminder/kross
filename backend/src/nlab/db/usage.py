"""Usage read from the ledger: tokens and estimated cost since 00:00 UTC, the daily limits, and the usage report."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, cast

from sqlalchemy import Select, String, case, delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.auth_sessions import utcnow
from nlab.db.errors import LimitReached
from nlab.db.models import BudgetReservation, DailyAdmission, LlmCall, PlaySession, User
from nlab.db.orgs import OrgContext

Prices = Mapping[str, tuple[float, float]]


@dataclass(frozen=True)
class Limits:
    """0 switches a limit off."""

    user_sessions_per_day: int
    user_tokens_per_day: int
    org_tokens_per_day: int
    daily_spend_usd: float
    prices: Prices = field(default_factory=dict)
    guest_sessions_per_day: int = 0  # per guest
    guest_tokens_per_day: int = 0  # per guest
    guest_total_tokens_per_day: int = 0  # all guests together
    guest_signups_per_day: int = 0  # new guests, all visitors together
    guest_signups_per_ip_per_day: int = 0  # new guests from one address
    max_concurrent_model_calls: int = 0  # in-flight provider calls in this process; 0 switches the cap off
    max_concurrent_paid_per_user: int = 0  # in-flight provider calls per account; 0 switches the cap off


@dataclass(frozen=True)
class Usage:
    calls: int
    tokens: int
    cost_usd: float


def start_of_day(moment: datetime) -> datetime:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def cost_of(model: str, tokens_in: int, tokens_out: int, prices: Prices) -> float:
    price_in, price_out = prices.get(model, (0.0, 0.0))
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def _by_model(since: datetime) -> Select[str, int, int, int]:
    return (
        select(
            LlmCall.model,
            func.count(),
            func.coalesce(func.sum(LlmCall.tokens_in), 0),
            func.coalesce(func.sum(LlmCall.tokens_out), 0),
        )
        .where(LlmCall.created_at >= since)
        .group_by(LlmCall.model)
    )


def _open_holds(
    since: datetime,
    *,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    guests_only: bool = False,
) -> Select[str, int, int]:
    """What every budget reservation created today still charges: its full reserved size while open (a call in
    flight, or one whose usage never became known), its settled actual usage afterwards. Ledger rows paid by a
    reservation are excluded from the quota sums (see usage_since), so a call is never counted twice."""
    charged_in = func.coalesce(
        func.sum(
            case((BudgetReservation.state == "open", BudgetReservation.reserved_in), else_=BudgetReservation.used_in)
        ),
        0,
    )
    charged_out = func.coalesce(
        func.sum(
            case((BudgetReservation.state == "open", BudgetReservation.reserved_out), else_=BudgetReservation.used_out)
        ),
        0,
    )
    query = select(BudgetReservation.model, charged_in, charged_out).where(BudgetReservation.created_at >= since)
    if guests_only:
        query = query.join(User, User.id == BudgetReservation.user_id).where(User.is_guest.is_(True))
    if user_id is not None:
        query = query.where(BudgetReservation.user_id == user_id)
    if org_id is not None:
        query = query.where(BudgetReservation.org_id == org_id)
    return query.group_by(BudgetReservation.model)


async def usage_since(
    db: AsyncSession,
    since: datetime,
    prices: Prices,
    *,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    guests_only: bool = False,
) -> Usage:
    """What today's limits count: the charges that are not covered by a budget reservation (direct ledger rows)
    plus every reservation's charge. Rows paid by a reservation carry its id and are excluded here; the completed
    analytics (usage_report) keep counting every ledger row."""
    query = _by_model(since).where(LlmCall.reservation_id.is_(None))
    if guests_only:  # a purged guest drops out of this sum; guests are only purged once their day is over
        query = query.join(User, User.id == LlmCall.user_id).where(User.is_guest.is_(True))
    if user_id is not None:
        query = query.where(LlmCall.user_id == user_id)
    if org_id is not None:
        query = query.where(LlmCall.org_id == org_id)
    calls = tokens = 0
    cost = 0.0
    for model, count, tokens_in, tokens_out in await db.execute(query):
        calls += count
        tokens += tokens_in + tokens_out
        cost += cost_of(model, tokens_in, tokens_out, prices)
    for model, reserved_in, reserved_out in await db.execute(
        _open_holds(since, user_id=user_id, org_id=org_id, guests_only=guests_only)
    ):
        held_in, held_out = int(reserved_in), int(reserved_out)  # SUM over BigInteger arrives as Decimal
        tokens += held_in + held_out
        cost += cost_of(model, held_in, held_out, prices)
    return Usage(calls=calls, tokens=tokens, cost_usd=cost)


LIFETIME = date(1970, 1, 1)  # the counter day for lifetime caps (one row per key, never reset at midnight)


async def admit(db: AsyncSession, *, scope: str, key: str, cap: int, message: str, lifetime: bool = False) -> None:
    """One atomic step of an admission counter. The upsert-then-compare runs in the caller's own short
    transaction: concurrent admissions serialise on the row, and a refusal rolls the step back (nothing is counted).
    A `cap` of 0 switches the limit off. `lifetime` counts per key forever instead of per UTC day."""
    day: date = LIFETIME if lifetime else start_of_day(utcnow()).date()
    counted = await db.scalar(
        insert(DailyAdmission)
        .values(day=day, scope=scope, key=key, count=1)
        .on_conflict_do_update(
            index_elements=[DailyAdmission.day, DailyAdmission.scope, DailyAdmission.key],
            set_={"count": DailyAdmission.count + 1},
        )
        .returning(DailyAdmission.count)
    )
    if cap and int(counted or 0) > cap:
        raise LimitReached(message)


async def purge_admissions(db: AsyncSession) -> int:
    """Old daily counters are derived data: drop daily rows older than two days (a run just after midnight still
    sees yesterday's), and lifetime coach rows only once their session is gone. Returns the rows removed."""
    cutoff = start_of_day(utcnow()).date() - timedelta(days=2)
    daily = cast(
        CursorResult[Any],
        await db.execute(
            delete(DailyAdmission).where(DailyAdmission.scope != "coach_question", DailyAdmission.day < cutoff)
        ),
    )
    coach = cast(
        CursorResult[Any],
        await db.execute(
            delete(DailyAdmission).where(
                DailyAdmission.scope == "coach_question",
                ~exists(select(PlaySession.id).where(PlaySession.id.cast(String) == DailyAdmission.key)),
            )
        ),
    )
    return int(daily.rowcount or 0) + int(coach.rowcount or 0)


async def admit_session_start(db: AsyncSession, limits: Limits, context: OrgContext) -> None:
    """Today's session starts are counted in their own durable row, not in the deletable play_sessions: deleting a
    transcript never restores the allowance."""
    if context.is_guest:
        await admit(
            db,
            scope="session_start",
            key=str(context.user_id),
            cap=limits.guest_sessions_per_day,
            message="Guests can start only a few sessions a day. Sign in for more, or return after 00:00 UTC.",
        )
    else:
        await admit(
            db,
            scope="session_start",
            key=str(context.user_id),
            cap=limits.user_sessions_per_day,
            message="You have started today's maximum number of sessions. It resets at 00:00 UTC.",
        )


async def check_guest_signups(db: AsyncSession, limits: Limits, ip: str | None = None) -> None:
    """Atomically admits one new guest against today's quotas: all visitors together, and this address alone.
    Raises LimitReached with a message for the visitor."""
    full = "Guest practice is full for today. Sign in, or come back after 00:00 UTC."
    if limits.guest_signups_per_day:
        await admit(db, scope="guest_signup", key="global", cap=limits.guest_signups_per_day, message=full)
    if ip and limits.guest_signups_per_ip_per_day:
        await admit(db, scope="guest_signup_ip", key=ip[:64], cap=limits.guest_signups_per_ip_per_day, message=full)


async def check_counts(
    db: AsyncSession,
    limits: Limits,
    *,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    is_guest: bool = False,
    extra_tokens: int = 0,
    extra_cost: float = 0.0,
) -> None:
    """Raises LimitReached, with a message for the user, when a limit is reached. Reads only. Counts read the
    charges that are not covered by a budget reservation plus every reservation's charge, so work in flight is
    never free. `extra` is the bounded worst case of the call being admitted: it must fit under every cap, and a
    caller already at a cap is refused either way."""
    since = start_of_day(utcnow())
    if limits.daily_spend_usd:
        spent = (await usage_since(db, since, limits.prices)).cost_usd
        if spent >= limits.daily_spend_usd or spent + extra_cost > limits.daily_spend_usd:
            raise LimitReached("The service has reached its daily budget. Practice resumes at 00:00 UTC.")
    if is_guest and user_id is not None:
        await _check_guest_limits(db, limits, user_id=user_id, since=since, extra_tokens=extra_tokens)
    if limits.user_tokens_per_day and user_id is not None:
        mine = await usage_since(db, since, limits.prices, user_id=user_id)
        if mine.tokens >= limits.user_tokens_per_day or mine.tokens + extra_tokens > limits.user_tokens_per_day:
            raise LimitReached("You have reached today's practice limit. It resets at 00:00 UTC.")
    if limits.org_tokens_per_day and org_id is not None:
        org = await usage_since(db, since, limits.prices, org_id=org_id)
        if org.tokens >= limits.org_tokens_per_day or org.tokens + extra_tokens > limits.org_tokens_per_day:
            raise LimitReached("Your organisation has reached today's practice limit. It resets at 00:00 UTC.")


async def check_limits(db: AsyncSession, limits: Limits, context: OrgContext) -> None:
    """The same checks as check_counts, for a caller that has its OrgContext."""
    await check_counts(db, limits, user_id=context.user_id, org_id=context.org_id, is_guest=context.is_guest)


@dataclass(frozen=True)
class DayUsage:
    day: str  # ISO date, UTC
    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: float


@dataclass(frozen=True)
class ModelUsage:
    model: str
    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: float


@dataclass(frozen=True)
class OrgUsage:
    org_id: uuid.UUID | None
    calls: int
    tokens: int
    cost_usd: float


async def usage_report(
    db: AsyncSession, days: int, prices: Prices
) -> tuple[list[DayUsage], list[ModelUsage], list[OrgUsage]]:
    """Per UTC day and per model over the last `days` days (today included), and per org for today."""
    today = start_of_day(utcnow())
    since = today - timedelta(days=days - 1)
    day = func.date_trunc("day", func.timezone("UTC", LlmCall.created_at))
    rows = await db.execute(
        select(
            day,
            LlmCall.model,
            func.count(),
            func.coalesce(func.sum(LlmCall.tokens_in), 0),
            func.coalesce(func.sum(LlmCall.tokens_out), 0),
        )
        .where(LlmCall.created_at >= since)
        .group_by(day, LlmCall.model)
    )
    per_day: dict[str, list[float]] = {}
    per_model: dict[str, list[float]] = {}
    for when, model, count, tokens_in, tokens_out in rows:
        cost = cost_of(model, tokens_in, tokens_out, prices)
        for key, table in ((when.date().isoformat(), per_day), (model, per_model)):
            totals = table.setdefault(key, [0, 0, 0, 0.0])
            totals[0] += count
            totals[1] += tokens_in
            totals[2] += tokens_out
            totals[3] += cost
    orgs = await db.execute(
        select(
            LlmCall.org_id,
            LlmCall.model,
            func.count(),
            func.coalesce(func.sum(LlmCall.tokens_in), 0),
            func.coalesce(func.sum(LlmCall.tokens_out), 0),
        )
        .where(LlmCall.created_at >= today)
        .group_by(LlmCall.org_id, LlmCall.model)
    )
    per_org: dict[uuid.UUID | None, list[float]] = {}
    for org_id, model, count, tokens_in, tokens_out in orgs:
        totals = per_org.setdefault(org_id, [0, 0, 0.0])
        totals[0] += count
        totals[1] += tokens_in + tokens_out
        totals[2] += cost_of(model, tokens_in, tokens_out, prices)
    return (
        [DayUsage(key, int(v[0]), int(v[1]), int(v[2]), v[3]) for key, v in sorted(per_day.items())],
        [ModelUsage(key, int(v[0]), int(v[1]), int(v[2]), v[3]) for key, v in sorted(per_model.items())],
        [OrgUsage(key, int(v[0]), int(v[1]), v[2]) for key, v in sorted(per_org.items(), key=lambda item: -item[1][2])],
    )


async def _check_guest_limits(
    db: AsyncSession, limits: Limits, *, user_id: uuid.UUID, since: datetime, extra_tokens: int = 0
) -> None:
    """The guest's own token caps, on top of the general ones (the session-start cap is counted by
    admit_session_start)."""
    if limits.guest_tokens_per_day:
        mine = await usage_since(db, since, limits.prices, user_id=user_id)
        if mine.tokens >= limits.guest_tokens_per_day or mine.tokens + extra_tokens > limits.guest_tokens_per_day:
            raise LimitReached(
                "You have reached today's guest practice limit. Sign in for more, or return after 00:00 UTC."
            )
    if limits.guest_total_tokens_per_day:
        everyone = await usage_since(db, since, limits.prices, guests_only=True)
        if (
            everyone.tokens >= limits.guest_total_tokens_per_day
            or everyone.tokens + extra_tokens > limits.guest_total_tokens_per_day
        ):
            raise LimitReached("Guest practice is full for today. Sign in, or come back after 00:00 UTC.")
