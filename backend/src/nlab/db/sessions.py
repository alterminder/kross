"""Play sessions and turns: who may read or watch a session, the lists, the transcript, and the claims that stop two
turns (or two scorers) running at once."""

import uuid
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import and_, delete, exists, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.auth_sessions import utcnow
from nlab.db.errors import Conflict, Gone, NotFound
from nlab.db.models import Mode, PlaySession, Scenario, ScenarioVersion, Status, Turn, TurnComment, User
from nlab.db.orgs import OrgContext
from nlab.db.scenarios import Entry
from nlab.engine import State
from nlab.llm import Line

# a turn claim older than this is treated as abandoned; claim tokens make a takeover safe, so the exact value
# only decides how fast an abandoned turn's slot is reused
CLAIM_TIMEOUT = timedelta(seconds=180)
SCORING_TIMEOUT = timedelta(minutes=5)  # a scoring claim older than this may be taken over


async def create_session(
    db: AsyncSession,
    context: OrgContext,
    entry: Entry,
    mode: Mode,
    rules: dict[str, object],
    state: State,
    opening: str,
) -> PlaySession:
    """A new session in the player's active org, with row 0 holding the counterpart's opening line."""
    session = PlaySession(
        org_id=context.org_id,
        user_id=context.user_id,
        scenario_id=entry.scenario.id,
        scenario_version_id=entry.version.id,
        mode=mode,
        rules=rules,
        engine_state=state.model_dump(mode="json"),
    )
    db.add(session)
    await db.flush()
    db.add(
        Turn(session_id=session.id, number=0, reply_text=opening, engine_state_after=session.engine_state, events=[])
    )
    await db.flush()
    return session


async def own_session(
    db: AsyncSession, context: OrgContext, session_id: uuid.UUID, for_update: bool = False
) -> PlaySession:
    """The caller's own session in their active org. `for_update` locks the row until the transaction ends, so a
    concurrent claim or turn serialises here instead of overwriting what this caller writes."""
    statement = select(PlaySession).where(
        PlaySession.id == session_id,
        PlaySession.user_id == context.user_id,
        PlaySession.org_id == context.org_id,
    )
    session = await db.scalar(statement.with_for_update() if for_update else statement)
    if session is None:
        raise NotFound("No such session")
    return session


async def readable_session(db: AsyncSession, context: OrgContext, session_id: uuid.UUID) -> PlaySession:
    """The player's own session, or a member's solo session for an admin of the session's org."""
    session = await db.scalar(
        select(PlaySession).where(PlaySession.id == session_id, PlaySession.org_id == context.org_id)
    )
    if session is None or not (session.user_id == context.user_id or (context.is_admin and session.mode == Mode.solo)):
        raise NotFound("No such session")
    return session


def may_watch(session: PlaySession, context: OrgContext) -> bool:
    """Live progress: an admin watching a member's solo session, or a playtester their own playtest. Never the player
    of a solo session, whatever their role (a personal org's owner is its admin)."""
    if session.mode == Mode.playtest:
        return session.user_id == context.user_id
    return context.is_admin and session.user_id != context.user_id


def may_steer(session: PlaySession, context: OrgContext) -> bool:
    """Whoever may watch, while the session is active: an org admin on a member's solo session, or the playtester on
    their own playtest. Never the player of a solo session."""
    return may_watch(session, context) and session.status == Status.active


async def steerable_session(
    db: AsyncSession, context: OrgContext, session_id: uuid.UUID, for_update: bool = False
) -> PlaySession:
    """The session a watcher steers or comments on: the caller's own session, or a member's solo session for an
    admin of the session's org (as readable_session), locked and refreshed when the caller is about to write."""
    statement = select(PlaySession).where(PlaySession.id == session_id, PlaySession.org_id == context.org_id)
    if for_update:
        # populate_existing: a locked reread must see what other transactions committed since this transaction's
        # earlier read (steer_twist reads the session, runs two model calls, then rereads and writes under this lock)
        statement = statement.with_for_update().execution_options(populate_existing=True)
    session = await db.scalar(statement)
    if session is None or not (session.user_id == context.user_id or (context.is_admin and session.mode == Mode.solo)):
        raise NotFound("No such session")
    return session


async def comments_of(db: AsyncSession, session_id: uuid.UUID) -> list[tuple[TurnComment, str]]:
    """The session's trainer comments with the author's current name, \"Former member\" for a deleted author."""
    rows = await db.execute(
        select(TurnComment, User.display_name)
        .outerjoin(User, User.id == TurnComment.author_id)
        .where(TurnComment.session_id == session_id)
        .order_by(TurnComment.created_at, TurnComment.turn)
    )
    return [(comment, name or "Former member") for comment, name in rows]


async def my_sessions(db: AsyncSession, context: OrgContext) -> list[tuple[PlaySession, Scenario, ScenarioVersion]]:
    rows = await db.execute(
        select(PlaySession, Scenario, ScenarioVersion)
        .join(Scenario, Scenario.id == PlaySession.scenario_id)
        .join(ScenarioVersion, ScenarioVersion.id == PlaySession.scenario_version_id)
        .where(PlaySession.user_id == context.user_id, PlaySession.org_id == context.org_id)
        .order_by(PlaySession.created_at.desc())
    )
    return [(session, scenario, version) for session, scenario, version in rows]


async def org_sessions(
    db: AsyncSession, context: OrgContext
) -> list[tuple[PlaySession, Scenario, ScenarioVersion, User]]:
    """The org's solo sessions, for its admins. Playtest sessions are not results and are left out."""
    rows = await db.execute(
        select(PlaySession, Scenario, ScenarioVersion, User)
        .join(Scenario, Scenario.id == PlaySession.scenario_id)
        .join(ScenarioVersion, ScenarioVersion.id == PlaySession.scenario_version_id)
        .join(User, User.id == PlaySession.user_id)
        .where(PlaySession.org_id == context.org_id, PlaySession.mode == Mode.solo)
        .order_by(PlaySession.created_at.desc())
    )
    return [(session, scenario, version, user) for session, scenario, version, user in rows]


async def version_of(db: AsyncSession, session: PlaySession) -> ScenarioVersion:
    return await db.get_one(ScenarioVersion, session.scenario_version_id)


async def turns_of(db: AsyncSession, session_id: uuid.UUID) -> list[Turn]:
    return list(await db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.number)))


def transcript(turns: list[Turn]) -> list[Line]:
    """The conversation as the LLM layer reads it: trainee line then reply, per turn; row 0 is the opening."""
    lines: list[Line] = []
    for turn in turns:
        speaker = (turn.engine_state_after or {}).get("active_interlocutor")
        if turn.trainee_text:
            lines.append(Line(role="trainee", text=turn.trainee_text, turn=turn.number, speaker=speaker))
        if turn.reply_text:
            lines.append(Line(role="character", text=turn.reply_text, turn=turn.number, speaker=speaker))
    return lines


async def claim_turn(db: AsyncSession, context: OrgContext, session_id: uuid.UUID) -> datetime:
    """Marks a turn as running, atomically, and returns the claim's token. 409 while another turn runs, 410 once the
    session has ended. The turn's writes are conditional on the token, so a claim taken over after a timeout cannot
    be finished (or released) by its original, still-running turn."""
    now = utcnow()
    claimed = await db.scalar(
        update(PlaySession)
        .where(
            PlaySession.id == session_id,
            PlaySession.user_id == context.user_id,
            PlaySession.org_id == context.org_id,
            PlaySession.status == Status.active,
            or_(PlaySession.turn_in_progress.is_(None), PlaySession.turn_in_progress < now - CLAIM_TIMEOUT),
        )
        .values(turn_in_progress=now)
        .returning(PlaySession.id)
    )
    if claimed is None:
        session = await own_session(db, context, session_id)
        if session.status != Status.active:
            raise Gone("This session has ended")
        raise Conflict("A turn is already running in this session")
    return now


async def release_turn(db: AsyncSession, session_id: uuid.UUID, token: datetime) -> None:
    """Frees this turn's own claim and nobody else's: a newer claim (a takeover) is left alone."""
    await db.execute(
        update(PlaySession)
        .where(PlaySession.id == session_id, PlaySession.turn_in_progress == token)
        .values(turn_in_progress=None)
    )


async def claim_finish(db: AsyncSession, session_id: uuid.UUID) -> datetime | None:
    """The token of this session's finish slot, or None when another finisher holds it. Reuses `turn_in_progress`
    (no turn can hold it once the session has ended): one finisher at a time, and a dead one's slot goes stale."""
    now = utcnow()
    claimed = await db.scalar(
        update(PlaySession)
        .where(
            PlaySession.id == session_id,
            PlaySession.status == Status.ended,
            or_(PlaySession.turn_in_progress.is_(None), PlaySession.turn_in_progress < now - SCORING_TIMEOUT),
        )
        .values(turn_in_progress=now)
        .returning(PlaySession.id)
    )
    return now if claimed is not None else None


async def claim_scoring(db: AsyncSession, turn_id: uuid.UUID) -> bool:
    """True if this caller may score the turn now: it is unscored and nobody (or only a stale scorer) holds it."""
    now = utcnow()
    claimed = await db.scalar(
        update(Turn)
        .where(
            Turn.id == turn_id,
            Turn.scores.is_(None),
            or_(Turn.scoring_started_at.is_(None), Turn.scoring_started_at < now - SCORING_TIMEOUT),
        )
        .values(scoring_started_at=now)
        .returning(Turn.id)
    )
    return claimed is not None


async def purge_sessions(db: AsyncSession, days: int) -> int:
    """Deletes sessions that ended more than `days` days ago, and abandoned ones (turns cascade). Abandoned means:
    created before the cutoff, no turn created since, and no turn claim set inside the window. The whole check is
    inside the DELETE, so a concurrent claim_turn serialises with it (Postgres re-checks the WHERE on a
    concurrently updated row). The recheck covers session-row columns only, not the EXISTS over turns — but a
    turn's final write needs a claim, so a session with no claim inside the window cannot gain a turn concurrently.
    The ledger keeps its rows: they hold only ids and counts. Returns how many sessions were deleted."""
    cutoff = utcnow() - timedelta(days=days)
    recent_turn = select(Turn.id).where(Turn.session_id == PlaySession.id, Turn.created_at >= cutoff)
    no_claim_in_window = or_(PlaySession.turn_in_progress.is_(None), PlaySession.turn_in_progress < cutoff)
    result = cast(
        CursorResult[PlaySession],
        await db.execute(
            delete(PlaySession).where(
                or_(
                    and_(PlaySession.ended_at.is_not(None), PlaySession.ended_at < cutoff),
                    and_(
                        PlaySession.ended_at.is_(None),
                        PlaySession.created_at < cutoff,
                        ~exists(recent_turn),
                        no_claim_in_window,
                    ),
                )
            )
        ),
    )
    return int(result.rowcount or 0)
