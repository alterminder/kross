"""Live steering: dials, preset twists fire through play.py's /inject; here free-text twists and comments."""

import uuid

from fastapi import APIRouter, HTTPException, Request

from nlab.api.budget import Actor, Budgeted
from nlab.api.deps import Db, OrgDep, llm_of, settings_of
from nlab.api.limits import limits_of
from nlab.api.play import clock_has_run_out, close_session, ensure_injects_allowed, progress_out
from nlab.api.schemas import CommentIn, CommentOut, DialIn, ProgressOut, SessionOut, TimeDecisionIn, TwistIn
from nlab.db.auth_sessions import utcnow
from nlab.db.errors import Conflict, Forbidden, Gone
from nlab.db.ledger import record_call, record_error
from nlab.db.models import PlaySession, Status, TurnComment, User
from nlab.db.orgs import OrgContext
from nlab.db.sessions import CLAIM_TIMEOUT, may_watch, steerable_session, turns_of, version_of
from nlab.db.usage import check_limits
from nlab.engine import State, inject_text, set_dial, time_up
from nlab.llm import CallFailed, MalformedAnswer, RoleName, check_bias, rewrite_twist
from nlab.llm.types import AdmissionDenied, InputTooLarge

router = APIRouter(prefix="/api/sessions", tags=["steer"])


def _target(session: PlaySession, context: OrgContext) -> PlaySession:
    """403 for the player of a solo session, 410 after the end, 409 while a turn runs — in that order."""
    if not may_watch(session, context):
        raise Forbidden("Steering is for watchers; the player of a solo session never steers it")
    if session.status == Status.ended:
        raise Gone("This session has ended")
    if session.turn_in_progress is not None and session.turn_in_progress > utcnow() - CLAIM_TIMEOUT:
        raise Conflict("A turn is still running")
    return session


@router.post("/{session_id}/dials")
async def steer_dial(session_id: uuid.UUID, body: DialIn, context: OrgDep, db: Db) -> ProgressOut:
    """A trainer override of one dial. It never ends the session; the next trainee message decides."""
    session = _target(await steerable_session(db, context, session_id, for_update=True), context)
    changed = set_dial(State.model_validate(session.engine_state), body.dial, body.value)
    session.engine_state = changed.state.model_dump(mode="json")
    session.turn_in_progress = None  # a stale turn's claim is invalidated: its write can no longer erase the override
    last = (await turns_of(db, session_id))[-1]
    last.events = [*last.events, *(event.model_dump(mode="json") for event in changed.events)]
    await db.commit()
    return await progress_out(db, session)


@router.post("/{session_id}/twists")
async def steer_twist(session_id: uuid.UUID, body: TwistIn, context: OrgDep, request: Request, db: Db) -> ProgressOut:
    """A free-text twist: the director rewrites it in character, the bias check flags it, and it is applied with the
    flag kept. No transaction stays open during the two model calls; they count toward the steering admin's limits."""
    provider, config = llm_of(request)
    await check_limits(db, limits_of(settings_of(request)), context)
    session = _target(await steerable_session(db, context, session_id), context)
    content = (await version_of(db, session)).content
    state = State.model_validate(session.engine_state)
    ensure_injects_allowed(content, state)  # before any paid call
    await db.commit()  # the read transaction ends here: no transaction is open during the model calls
    ids = {"user_id": context.user_id, "org_id": context.org_id, "session_id": session.id}
    provider = Budgeted(
        provider,
        request.app.state.sessionmaker,
        Actor(context.user_id, context.org_id, session.id, is_guest=context.is_guest),
        lambda: settings_of(request),
    )
    role: RoleName = "director"  # the call in flight: a provider failure is charged to the role that failed
    try:
        rewritten = await rewrite_twist(provider, config, content, state, body.text)
        record_call(db, rewritten.record, **ids)
        await db.commit()  # the ledger row lands before the next model call, and no transaction spans it
        role = "bias"
        bias = await check_bias(provider, config, body.text, rewritten.value)
        record_call(db, bias.record, **ids)
        await db.commit()  # paid calls stay in the ledger even when the locked write below is refused
    except (AdmissionDenied, InputTooLarge):
        raise
    except MalformedAnswer as exc:
        record_call(db, exc.record, **ids)
        await db.commit()
        raise HTTPException(502, "The model's answer was unusable. Try again.") from exc
    except CallFailed as exc:  # a paid partial failure: its usage and attempts reach the ledger
        record_call(db, exc.record, **ids)
        await db.commit()
        raise HTTPException(502, "The language model did not answer. Try again.") from exc
    except Exception as exc:
        record_error(db, role, config.for_role(role).model, **ids)
        await db.commit()
        raise HTTPException(502, "The language model did not answer. Try again.") from exc
    session = _target(await steerable_session(db, context, session_id, for_update=True), context)
    ensure_injects_allowed(content, State.model_validate(session.engine_state))  # the stage may have changed meanwhile
    twist = inject_text(
        State.model_validate(session.engine_state), body.text, rewritten.value, bias.value.model_dump(mode="json")
    )
    session.engine_state = twist.state.model_dump(mode="json")
    session.turn_in_progress = None  # a stale turn's claim is invalidated: its write can no longer erase the twist
    last = (await turns_of(db, session_id))[-1]
    last.events = [*last.events, *(event.model_dump(mode="json") for event in twist.events)]
    await db.commit()
    return await progress_out(db, session)


@router.post("/{session_id}/time-decision")
async def decide_time_up(
    session_id: uuid.UUID, body: TimeDecisionIn, context: OrgDep, request: Request, db: Db
) -> SessionOut:
    """The trainer ends a meeting whose time has run out, with or without a result. Only for a scenario whose
    `on_timeout` is "trainer", once the server's clock agrees that the time is up."""
    session = _target(await steerable_session(db, context, session_id, for_update=True), context)
    content = (await version_of(db, session)).content
    if (content.get("timing") or {}).get("on_timeout") != "trainer":
        raise Conflict("This scenario does not leave the end to the trainer")
    if not clock_has_run_out(session, content):
        raise Conflict("There is time left")
    ended = time_up(State.model_validate(session.engine_state), fail=body.result == "fail")
    return await close_session(request, db, session, ended)


@router.post("/{session_id}/comments", status_code=201)
async def comment(session_id: uuid.UUID, body: CommentIn, context: OrgDep, db: Db) -> CommentOut:
    """A trainer's note on one turn, during play and after the end. The player never sees comments."""
    session = await steerable_session(db, context, session_id)
    if not may_watch(session, context):
        raise Forbidden("Comments are for watchers; the player of a solo session never sees them")
    if body.turn not in {turn.number for turn in await turns_of(db, session_id)}:
        raise HTTPException(422, "This session has no such turn")
    row = TurnComment(session_id=session.id, turn=body.turn, author_id=context.user_id, text=body.text)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    author = await db.get_one(User, context.user_id)
    return CommentOut(turn=row.turn, text=row.text, author=author.display_name, created_at=row.created_at)
