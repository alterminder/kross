"""Playing a scenario: start a session, send turns (streamed), end it, read the debrief; admins watch progress."""

import json
import logging
import uuid
from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Literal

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.api.budget import Actor, Budgeted
from nlab.api.deps import Db, OrgDep, ViewerDep, budgeted_llm_of, content_of, settings_of
from nlab.api.limits import limits_of
from nlab.api.scenarios import readable_cover_versions
from nlab.api.schemas import (
    CoachCitationOut,
    CoachMessageIn,
    CoachSuggestionsOut,
    CommentOut,
    DebriefOut,
    DialCauseOut,
    HiddenFactOut,
    InjectIn,
    InjectionOut,
    InterlocutorIn,
    LineOut,
    OutcomeOut,
    PartyDialsOut,
    PhaseOut,
    PlayerOutcome,
    PreparationIn,
    ProgressOut,
    ReflectionIn,
    SessionCard,
    SessionOut,
    StartIn,
    TurnIn,
    TurnProgress,
)
from nlab.api.scoring import finish_session, score_turn
from nlab.db.auth_sessions import utcnow
from nlab.db.errors import Conflict, Forbidden, Gone
from nlab.db.ledger import record_call, record_error
from nlab.db.models import Mode, PlaySession, Scenario, ScenarioVersion, Status, Turn, User
from nlab.db.orgs import OrgContext
from nlab.db.rules import org_overrides, pinned_rules
from nlab.db.scenarios import can_edit, can_review, get_entry
from nlab.db.sessions import (
    CLAIM_TIMEOUT,
    claim_turn,
    comments_of,
    create_session,
    may_watch,
    my_sessions,
    org_sessions,
    own_session,
    readable_session,
    release_turn,
    steerable_session,
    transcript,
    turns_of,
    version_of,
)
from nlab.db.usage import admit, admit_session_start, check_limits
from nlab.engine import (
    Rubric,
    Rules,
    State,
    Step,
    end,
    grant,
    grantable,
    inject,
    is_red_line,
    nudge,
    start,
    step,
    time_up,
)
from nlab.engine import Scenario as EngineScenario
from nlab.engine.cchn_debrief import compute_cchn_debrief
from nlab.engine.conditions import NEVER, describe
from nlab.engine.state import Classification
from nlab.knowledge import get_knowledge_base
from nlab.llm import (
    CallFailed,
    CoachStream,
    CounterpartStream,
    Line,
    LLMConfig,
    MalformedAnswer,
    NoAnswer,
    Provider,
    classify,
    coach_refusal,
    coach_request,
    coach_scope,
    counterpart_request,
    grant_check,
    phase_at,
    phases_of,
)
from nlab.llm.types import AdmissionDenied, InputTooLarge

router = APIRouter(prefix="/api/sessions", tags=["play"])
logger = logging.getLogger(__name__)
PLACEHOLDER = "(The counterpart does not answer. You can continue.)"
DEBRIEF_RETRY_AFTER = timedelta(minutes=5)  # a debrief still pending this long after the end is an orphan


def _outcome(state: State) -> PlayerOutcome | None:
    return PlayerOutcome(result=state.outcome.result, label=state.outcome.label) if state.outcome else None


def _silent(state: State, rules: Rules) -> bool:
    """The plan's No-reply rule: after a red line or a move's ends_session (the insult) the counterpart says
    nothing more."""
    if is_red_line(state.outcome):
        return True
    endings = {move.ends_session.id for move in rules.moves.values() if move.ends_session}
    return state.outcome is not None and state.outcome.id in endings


def hidden_facts_of(content: Mapping[str, Any], rules: Rules, state: State) -> list[HiddenFactOut]:
    """What the counterpart held back and what the trainee drew out of it, for the debrief. The unlock sentence is
    given only for a fact that stayed hidden: the scenario's own reveal rule, or the rules' default for its layer."""
    facts = []
    for interest in EngineScenario.from_content(content).counterpart.hidden_interests:
        found = interest.id in state.revealed
        condition = interest.reveal_when or rules.hidden_interest_reveal_defaults.get(interest.layer, NEVER)
        facts.append(
            HiddenFactOut(id=interest.id, text=interest.text, found=found, unlock="" if found else describe(condition))
        )
    return facts


def dial_causes_of(turns: Sequence[Turn], state: State) -> list[DialCauseOut]:
    """Every dial change worth explaining, grouped by turn and cause. A move carries the trainee's quote. Silence, a
    twist (preset, automatic or free text) and a trainer override are named as what they were, never as the trainee's
    words. The engine's own upkeep (consistency recovering) is left out."""
    twists = {item.id: item.label for item in state.injections}
    rows: dict[tuple[int, str, str], DialCauseOut] = {}
    for turn in turns:
        for event in turn.events:
            before, after, dial = event.get("before"), event.get("after"), event.get("dial")
            if event.get("kind") != "dial" or dial is None or before is None or after is None or before == after:
                continue
            source, ref = str(event.get("source")), str(event.get("ref") or "")
            reason = str(event.get("reason") or "")
            if source == "move":
                kind, label, quote = "move", ref.replace("_", " "), str(event.get("quote") or "")
            elif source == "auto" and reason.startswith("Trainee silence"):
                kind, label, quote, ref = "silence", "You stayed silent", "", "silence"
            elif source == "trainer" and reason == "manual override":
                kind, label, quote, ref = "trainer", "A trainer's adjustment", "", "override"
            elif source in ("auto", "trainer") and ref:
                kind, label, quote = "twist", twists.get(ref, ref), ""
            else:
                continue
            row = rows.setdefault(
                (int(event["turn"]), kind, ref),
                DialCauseOut(turn=int(event["turn"]), kind=kind, label=label, quote=quote, changes={}),
            )
            row.changes[str(dial)] = row.changes.get(str(dial), 0) + (after - before)
    return [row for row in rows.values() if any(row.changes.values())]


def dimension_names(rubric: Rubric, ids: Collection[str]) -> dict[str, str]:
    """The rubric's name for each of the scenario's dimensions (the id, tidied, when the rubric has none)."""
    labels = {
        key: str(value.get("label") or "") if isinstance(value, dict) else ""
        for cluster in rubric.clusters.values()
        for key, value in cluster.dimensions.items()
    }
    return {key: labels.get(key) or key.replace("_", " ").capitalize() for key in ids}


def seconds_left_of(session: PlaySession, content: Mapping[str, Any]) -> tuple[int | None, int | None]:
    """(the scenario's minutes, the seconds still left of them) for an active session. The clock runs from the
    session's start and is a guide: nothing ends the session when it reaches zero."""
    minutes = content.get("estimated_minutes")
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
        return None, None
    if session.status != Status.active:
        return minutes, None
    left = minutes * 60 - (utcnow() - session.created_at).total_seconds()
    return minutes, max(0, round(left))


async def session_out(db: AsyncSession, session: PlaySession) -> SessionOut:
    version = await version_of(db, session)
    scenario = await db.get_one(Scenario, session.scenario_id)
    state = State.model_validate(session.engine_state)
    content = version.content
    brief = dict(content.get("trainee_brief") or {})
    if "counterpart_role" not in brief:
        cps = content.get("counterparts") or []
        if cps and isinstance(cps, list) and len(cps) > 0 and isinstance(cps[0], dict):
            brief["counterpart_role"] = cps[0].get("role") or cps[0].get("id")
    if "estimated_minutes" not in brief and content.get("estimated_minutes"):
        brief["estimated_minutes"] = content.get("estimated_minutes")
    if "difficulty" not in brief and content.get("difficulty"):
        brief["difficulty"] = content.get("difficulty")
    phase = phase_at(content, state.turn).id
    brief["phase"] = phase
    timing = content.get("timing") or {}
    minutes_total, seconds_left = seconds_left_of(session, content)
    engine_scenario = EngineScenario.from_content(content)
    prep_spec = engine_scenario.preparation
    counterparts = (
        [
            {
                "id": str(cp.id or ""),
                "role": str(cp.role or ""),
                "persona": str(cp.persona or ""),
                "cultural_profile": str(cp.cultural_profile or ""),
                "stated_position": str(cp.stated_position or ""),
            }
            for cp in engine_scenario.counterparts
        ]
        if engine_scenario.counterparts
        else [
            {
                "id": "counterpart",
                "role": str(content.get("counterpart_role") or "Counterpart"),
                "persona": "",
                "cultural_profile": "",
                "stated_position": str(engine_scenario.counterpart.stated_position or ""),
            }
        ]
    )
    stakeholders = [
        {
            "id": str(sh.get("id") or ""),
            "role": str(sh.get("role") or ""),
            "persona": str(sh.get("persona") or ""),
            "influence": str(sh.get("influence") or "medium"),
            "stance": str(sh.get("stance") or "transformative"),
            "scope": str(sh.get("scope") or "local"),
        }
        for sh in engine_scenario.stakeholders
    ]
    active_interlocutor = state.active_interlocutor or (counterparts[0]["id"] if counterparts else "counterpart")
    multiparty = engine_scenario.multiparty.model_dump() if engine_scenario.multiparty else None

    return SessionOut(
        id=session.id,
        scenario_id=session.scenario_id,
        title=str(content.get("title") or scenario.title),
        cover=scenario.cover,
        mode=session.mode,
        status=session.status,
        turn=state.turn,
        turn_running=session.status == Status.active and session.turn_in_progress is not None,
        brief=brief,
        transcript=[LineOut(**line.model_dump()) for line in transcript(await turns_of(db, session.id))],
        outcome=_outcome(state) if session.status == Status.ended else None,
        debrief_status=session.debrief_status,
        phase=phase,
        phases=[PhaseOut(id=item.id, label=item.label, hint=item.hint) for item in phases_of(content)],
        minutes_total=minutes_total,
        seconds_left=seconds_left,
        warning_minutes=sorted(timing.get("warnings") or [5, 1], reverse=True),
        on_timeout=timing.get("on_timeout") or "guide",
        silence_seconds=(timing.get("silence") or {}).get("after_seconds") or 90,
        preparation=session.preparation,
        preparation_modules=prep_spec.modules,
        preparation_minutes=prep_spec.time_limit_minutes,
        reflection=session.reflection,
        counterparts=counterparts,
        stakeholders=stakeholders,
        active_interlocutor=active_interlocutor,
        multiparty=multiparty,
    )


@router.post("", status_code=201)
async def start_session(body: StartIn, viewer: ViewerDep, request: Request, db: Db) -> SessionOut:
    limits = limits_of(settings_of(request))
    await check_limits(db, limits, viewer.context)
    await admit_session_start(db, limits, viewer.context)  # durable: deleting the session never restores it
    entry = await get_entry(db, viewer, body.scenario_id)
    if body.mode == Mode.playtest and not (can_edit(entry.scenario, viewer) or can_review(entry.scenario, viewer)):
        raise Forbidden("Only the scenario's editors can playtest it")
    scenario = EngineScenario.from_content(entry.version.content)
    rules = pinned_rules(
        content_of(request).raw_rules,
        await org_overrides(db, viewer.context.org_id),
        scenario.overrides,
    )
    begun = start(scenario, Rules.model_validate(rules))
    session = await create_session(db, viewer.context, entry, body.mode, rules, begun.state, begun.opening or "")
    await db.commit()
    return await session_out(db, session)


@router.get("")
async def list_sessions(
    viewer: ViewerDep, context: OrgDep, db: Db, scope: Literal["mine", "org"] = "mine"
) -> list[SessionCard]:
    if scope == "org":
        if not context.is_admin:
            raise Forbidden("Only an admin of this org can list its sessions")
        rows = await org_sessions(db, context)
        versions = await readable_cover_versions(db, viewer, [scenario.id for _, scenario, _, _ in rows])
        return [
            _card(session, scenario, version, user.display_name, user.id, versions.get(scenario.id))
            for session, scenario, version, user in rows
        ]
    mine = await my_sessions(db, context)
    versions = await readable_cover_versions(db, viewer, [scenario.id for _, scenario, _ in mine])
    return [
        _card(session, scenario, version, None, None, versions.get(scenario.id)) for session, scenario, version in mine
    ]


def _card(
    session: PlaySession,
    scenario: Scenario,
    version: ScenarioVersion,
    player: str | None,
    player_id: uuid.UUID | None,
    cover_version: str | None = None,
) -> SessionCard:
    state = State.model_validate(session.engine_state)
    ended = session.status == Status.ended and state.outcome is not None
    return SessionCard(
        id=session.id,
        scenario_id=session.scenario_id,
        title=str(version.content.get("title") or scenario.title),  # the pinned title, as SessionOut shows it
        cover=scenario.cover,
        cover_image_version=cover_version,
        mode=session.mode,
        status=session.status,
        turn=state.turn,
        result=state.outcome.result if ended and state.outcome else None,
        player=player,
        player_id=player_id,
        created_at=session.created_at,
    )


@router.get("/{session_id}")
async def read_session(session_id: uuid.UUID, context: OrgDep, db: Db) -> SessionOut:
    return await session_out(db, await readable_session(db, context, session_id))


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: uuid.UUID, context: OrgDep, db: Db) -> None:
    """The player deletes their own session; the turns, scores, comments and debrief go with it."""
    await db.delete(await own_session(db, context, session_id, for_update=True))
    await db.commit()


async def _valid_interlocutor_ids(db: AsyncSession, session: PlaySession) -> set[str]:
    """Every interlocutor id a turn or a switch may name: the scenario's counterparts and stakeholders, or the
    single implicit counterpart of a legacy scenario."""
    version = await version_of(db, session)
    engine_scenario = EngineScenario.from_content(version.content)
    valid_ids: set[str] = {cp.id for cp in engine_scenario.counterparts}
    valid_ids |= {sh["id"] for sh in engine_scenario.stakeholders if sh.get("id")}
    return valid_ids or {"counterpart"}


@router.put("/{session_id}/preparation")
async def save_preparation(session_id: uuid.UUID, body: PreparationIn, viewer: ViewerDep, db: Db) -> SessionOut:
    session = await own_session(db, viewer.context, session_id, for_update=True)
    if session.status != Status.active:
        raise Gone("The session has ended")
    session.preparation = body.model_dump(mode="json", exclude_none=True)
    await db.commit()
    return await session_out(db, session)


@router.put("/{session_id}/reflection")
async def save_reflection(session_id: uuid.UUID, body: ReflectionIn, viewer: ViewerDep, db: Db) -> SessionOut:
    session = await own_session(db, viewer.context, session_id, for_update=True)
    if session.status != Status.ended:
        raise Gone("The reflection comes after the session ends")
    session.reflection = body.answers
    await db.commit()
    return await session_out(db, session)


def sse(event: str, data: Mapping[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


@router.post("/{session_id}/interlocutor")
async def set_interlocutor(session_id: uuid.UUID, body: InterlocutorIn, viewer: ViewerDep, db: Db) -> SessionOut:
    session = await own_session(db, viewer.context, session_id, for_update=True)
    if session.status != Status.active:
        raise Forbidden("The session has ended")
    if body.interlocutor not in (await _valid_interlocutor_ids(db, session)):
        raise HTTPException(400, f"Unknown interlocutor: {body.interlocutor}")
    state = State.model_validate(session.engine_state)
    state.active_interlocutor = body.interlocutor
    if body.interlocutor in state.counterpart_dials:
        state.dials = state.counterpart_dials[body.interlocutor]
    session.engine_state = state.model_dump(mode="json")
    await db.commit()
    return await session_out(db, session)


class TurnStream(StreamingResponse):
    """Starlette never closes the body iterator: a generator parked at a yield when the client leaves would run its
    cleanup only when the garbage collector finds it."""

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()  # type: ignore[attr-defined]  # runs _turn's finally now


@router.post("/{session_id}/turns")
async def take_turn(
    session_id: uuid.UUID, body: TurnIn, context: OrgDep, request: Request, db: Db
) -> StreamingResponse:
    """One trainee message. The answer is a stream of events: reply chunks, then done (or error)."""
    provider, config = budgeted_llm_of(  # 503 before anything is claimed; every billed call reserves first
        request, Actor(context.user_id, context.org_id, session_id, context.is_guest)
    )
    await check_limits(db, limits_of(settings_of(request)), context)
    await _end_if_time_is_up(db, context, request, session_id)
    if body.interlocutor is not None:
        session = await own_session(db, context, session_id)
        if body.interlocutor not in (await _valid_interlocutor_ids(db, session)):
            raise HTTPException(400, f"Unknown interlocutor: {body.interlocutor}")
    token = await claim_turn(db, context, session_id)
    await db.commit()
    app = request.app
    return TurnStream(
        _turn(
            app.state.sessionmaker,
            app.state.background,
            provider,
            config,
            session_id,
            body.text,
            token,
            content_of(request).rubric,
            interlocutor=body.interlocutor,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _turn(
    maker: Any,
    background: Any,
    provider: Provider,
    config: LLMConfig,
    session_id: uuid.UUID,
    text: str,
    token: datetime,
    rubric: Rubric | None = None,
    interlocutor: str | None = None,
) -> AsyncIterator[bytes]:
    """The turn pipeline (docs/architecture/README.md, steps 3-8), in its own database session (the request's own
    session is torn down only after the response finishes; this pipeline never touches it). Whatever happens, the
    claim is released: on success by the final commit, otherwise in `finally`."""
    completed = False
    db = maker()
    try:
        session = await db.get_one(PlaySession, session_id)
        ids = {"user_id": session.user_id, "org_id": session.org_id, "session_id": session.id}
        content = (await version_of(db, session)).content
        scenario = EngineScenario.from_content(content)
        rules = Rules.model_validate(session.rules)
        state = State.model_validate(session.engine_state)
        before = transcript(await turns_of(db, session_id))
        await db.commit()  # the read transaction ends here: no transaction is open during the model calls
        try:
            classified = await classify(provider, config, content, rules, before, text, state.offered)
        except (AdmissionDenied, InputTooLarge) as exc:  # refused before the provider call: nothing is billed
            yield sse("error", {"detail": str(exc)})
            return
        except MalformedAnswer as exc:
            record_call(db, exc.record, **ids)
            yield sse("error", {"detail": "The model's answer was unusable. Send your message again."})
            return
        except CallFailed as exc:  # a paid partial failure: its usage and attempts reach the ledger
            # the log names the wrapped failure's type only: exception text and chains can carry provider replies
            logger.warning("Classifier call failed (%s)", type(exc.__cause__ or exc).__name__)
            record_call(db, exc.record, **ids)
            yield sse("error", {"detail": "The language model did not answer. Send your message again."})
            return
        except Exception as exc:
            logger.warning("Classifier call failed (%s)", type(exc).__name__)
            record_error(db, "classifier", config.for_role("classifier").model, **ids)
            yield sse("error", {"detail": "The language model did not answer. Send your message again."})
            return
        record_call(db, classified.record, **ids)
        await db.commit()  # the ledger row lands before the next model call, and no transaction spans it
        stepped = step(scenario, rules, state, text, classified.value, interlocutor=interlocutor)
        state, events = stepped.state, list(stepped.events)
        lines = [*before, Line(role="trainee", text=text, turn=state.turn)]
        reply: str | None = None
        said_fallback = False  # the counterpart gave no answer: nothing in `reply` is the model's to be checked
        frozen: dict[str, Any] | None = None
        active_speaker = state.active_interlocutor
        if not _silent(state, rules):
            try:
                request = counterpart_request(
                    config,
                    content,
                    state,
                    lines,
                    [rule.text for rule in rules.avatar_rules],
                    interlocutor_id=active_speaker,
                )
                frozen = request.model_dump(mode="json")
                stream = CounterpartStream(provider, config.for_role("counterpart"), request)
                async for chunk in stream:
                    yield sse("reply", {"text": chunk})
                reply = stream.text
                if stream.record is not None:
                    record_call(db, stream.record, **ids)
            except (AdmissionDenied, InputTooLarge) as exc:  # refused before the call: the turn does not happen
                yield sse("error", {"detail": str(exc)})
                return
            except NoAnswer as exc:
                record_call(db, exc.record, **ids)
                # the fallback is the primary counterpart's own voice; any other speaker gets the neutral placeholder
                primary = scenario.counterparts[0] if scenario.counterparts else scenario.counterpart
                own_voice = primary.fallback if (not active_speaker or active_speaker == primary.id) else None
                reply = own_voice or PLACEHOLDER
                if own_voice:
                    yield sse("reply", {"text": reply})
                else:
                    yield sse("notice", {"detail": PLACEHOLDER})
                said_fallback = True
            except Exception as exc:
                logger.warning("Counterpart call failed (%s)", type(exc).__name__)
                record_error(db, "counterpart", config.for_role("counterpart").model, **ids)
                yield sse("error", {"detail": "The language model did not answer. Send your message again."})
                return  # the turn did not happen; nothing is saved (the partial stream cannot be unsent)
            await db.commit()  # again: nothing open over the grant check below
            lines.append(Line(role="character", text=reply, turn=state.turn, speaker=active_speaker))
            if grantable(state) and state.offered is not None and not said_fallback:
                try:
                    checked = await grant_check(provider, config, state.offered, lines)
                except AdmissionDenied:  # refused before the provider call: the reply is already shown, so the
                    pass  # turn counts, not granted; nothing is billed and no ledger row is written
                except MalformedAnswer as exc:
                    record_call(db, exc.record, **ids)
                except CallFailed as exc:  # a paid partial failure: the turn counts, not granted
                    logger.warning("Grant check failed (%s)", type(exc.__cause__ or exc).__name__)
                    record_call(db, exc.record, **ids)
                except Exception as exc:
                    # the reply was already shown, so the turn counts: not granted, nothing else changes
                    logger.warning("Grant check failed (%s)", type(exc).__name__)
                    record_error(db, "grant", config.for_role("grant").model, **ids)
                else:
                    record_call(db, checked.record, **ids)
                    if checked.value:
                        granted = grant(scenario, state, checked.value)
                        state, events = granted.state, [*events, *granted.events]
            await db.commit()  # the grant's ledger row lands even if the final write below loses
        engine_state = state.model_dump(mode="json")
        ended = state.outcome is not None
        values: dict[str, Any] = {"engine_state": engine_state, "turn_in_progress": None}
        if ended:
            values |= {"status": Status.ended, "ended_at": utcnow(), "debrief_status": "pending"}
        saved = await db.scalar(
            update(PlaySession)
            .where(
                PlaySession.id == session.id,
                PlaySession.status == Status.active,
                PlaySession.turn_in_progress == token,
            )
            .values(**values)
            .returning(PlaySession.id)
        )
        if saved is None:  # /end, /inject or a takeover changed the session while the model was working
            await db.rollback()
            yield sse("error", {"detail": "The session changed while the model was working; nothing was saved."})
            return
        db.add(  # only a write that won the session row may create its turn row
            Turn(
                session_id=session.id,
                number=state.turn,
                trainee_text=text,
                reply_text=reply,
                classification=classified.value.model_dump(mode="json"),
                engine_state_after=engine_state,
                events=[event.model_dump(mode="json") for event in events],
                counterpart_request=frozen,
            )
        )
        await db.commit()
        completed = True
        background.spawn(score_turn(maker, provider, config, session.id, state.turn, rubric))
        if ended:
            background.spawn(finish_session(maker, provider, config, session.id, rubric))
        outcome = _outcome(state) if ended else None
        yield sse("done", {"turn": state.turn, "ended": ended, "outcome": outcome.model_dump() if outcome else None})
    finally:
        # shielded: a client disconnect cancels this generator's scope, and an unshielded cleanup would be
        # cancelled at its first await, leaving the turn claimed (and the connection half-closed)
        with anyio.CancelScope(shield=True):
            try:
                if not completed:  # an error, an early return or a disconnect: keep the ledger rows, free the claim
                    try:
                        await release_turn(db, session_id, token)
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        fresh = maker()
                        try:
                            await release_turn(fresh, session_id, token)
                            await fresh.commit()
                        finally:
                            await fresh.close()
            finally:  # every path closes the session, including the success path and a broken connection
                await db.close()


@router.post("/{session_id}/nudge")
async def take_nudge(session_id: uuid.UUID, context: OrgDep, request: Request, db: Db) -> StreamingResponse:
    """An inactivity/silence nudge: when the trainee has been silent, the counterpart prompts them in-character."""
    provider, config = budgeted_llm_of(request, Actor(context.user_id, context.org_id, session_id, context.is_guest))
    await check_limits(db, limits_of(settings_of(request)), context)
    await _end_if_time_is_up(db, context, request, session_id)
    token = await claim_turn(db, context, session_id)
    await db.commit()
    app = request.app
    return TurnStream(
        _nudge(
            app.state.sessionmaker,
            app.state.background,
            provider,
            config,
            session_id,
            token,
            content_of(request).rubric,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _nudge(
    maker: Any,
    background: Any,
    provider: Provider,
    config: LLMConfig,
    session_id: uuid.UUID,
    token: datetime,
    rubric: Rubric | None = None,
) -> AsyncIterator[bytes]:
    completed = False
    db = maker()
    try:
        session = await db.get_one(PlaySession, session_id)
        ids = {"user_id": session.user_id, "org_id": session.org_id, "session_id": session.id}
        content = (await version_of(db, session)).content
        scenario = EngineScenario.from_content(content)
        rules = Rules.model_validate(session.rules)
        state = State.model_validate(session.engine_state)
        before = transcript(await turns_of(db, session_id))
        await db.commit()

        stepped = nudge(scenario, rules, state)
        state, events = stepped.state, list(stepped.events)

        silence_text = "(The delegate remains silent.)"
        lines = [*before, Line(role="trainee", text=silence_text, turn=state.turn)]
        reply: str | None = None
        frozen: dict[str, Any] | None = None
        spoken = scenario.timing.silence.line
        if spoken and not _silent(state, rules):
            reply = spoken  # the scenario's own words for a silence: no model call
            yield sse("reply", {"text": spoken})
            lines.append(Line(role="character", text=reply, turn=state.turn, speaker=state.active_interlocutor))
        elif not _silent(state, rules):
            request = counterpart_request(
                config,
                content,
                state,
                lines,
                [rule.text for rule in rules.avatar_rules],
                interlocutor_id=state.active_interlocutor,
            )
            frozen = request.model_dump(mode="json")
            stream = CounterpartStream(provider, config.for_role("counterpart"), request)
            try:
                async for chunk in stream:
                    yield sse("reply", {"text": chunk})
                reply = stream.text
                if stream.record is not None:
                    record_call(db, stream.record, **ids)
            except (AdmissionDenied, InputTooLarge) as exc:  # refused before the call: the nudge does not happen
                yield sse("error", {"detail": str(exc)})
                return
            except NoAnswer as exc:
                record_call(db, exc.record, **ids)
                # the fallback is the primary counterpart's own voice; any other speaker gets the neutral placeholder
                primary = scenario.counterparts[0] if scenario.counterparts else scenario.counterpart
                own_voice = (
                    primary.fallback
                    if (not state.active_interlocutor or state.active_interlocutor == primary.id)
                    else None
                )
                reply = own_voice or PLACEHOLDER
                if own_voice:
                    yield sse("reply", {"text": reply})
                else:
                    yield sse("notice", {"detail": PLACEHOLDER})
            except Exception as exc:
                logger.warning("Counterpart nudge call failed (%s)", type(exc).__name__)
                record_error(db, "counterpart", config.for_role("counterpart").model, **ids)
                yield sse("error", {"detail": "The language model did not answer."})
                return
            await db.commit()
            lines.append(Line(role="character", text=reply, turn=state.turn, speaker=state.active_interlocutor))

        engine_state = state.model_dump(mode="json")
        ended = state.outcome is not None
        values: dict[str, Any] = {"engine_state": engine_state, "turn_in_progress": None}
        if ended:
            values |= {"status": Status.ended, "ended_at": utcnow(), "debrief_status": "pending"}
        saved = await db.scalar(
            update(PlaySession)
            .where(
                PlaySession.id == session.id,
                PlaySession.status == Status.active,
                PlaySession.turn_in_progress == token,
            )
            .values(**values)
            .returning(PlaySession.id)
        )
        if saved is None:
            await db.rollback()
            yield sse("error", {"detail": "The session changed while the model was working; nothing was saved."})
            return
        db.add(
            Turn(
                session_id=session.id,
                number=state.turn,
                trainee_text=silence_text,
                reply_text=reply,
                classification=Classification().model_dump(mode="json"),
                engine_state_after=engine_state,
                events=[event.model_dump(mode="json") for event in events],
                counterpart_request=frozen,
            )
        )
        await db.commit()
        completed = True
        background.spawn(score_turn(maker, provider, config, session.id, state.turn, rubric))
        if ended:
            background.spawn(finish_session(maker, provider, config, session.id, rubric))
        outcome = _outcome(state) if ended else None
        yield sse("done", {"turn": state.turn, "ended": ended, "outcome": outcome.model_dump() if outcome else None})
    finally:
        with anyio.CancelScope(shield=True):
            try:
                if not completed:
                    try:
                        await release_turn(db, session_id, token)
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        fresh = maker()
                        try:
                            await release_turn(fresh, session_id, token)
                            await fresh.commit()
                        finally:
                            await fresh.close()
            finally:
                await db.close()


async def close_session(
    request: Request, db: AsyncSession, session: PlaySession, ended: Step, is_guest: bool = False
) -> SessionOut:
    """Ends a session with the engine's closing step: the state, the status, the last turn's events, and the debrief
    in the background. The caller holds the row lock and has checked that nothing is running."""
    session.engine_state = ended.state.model_dump(mode="json")
    session.status = Status.ended
    session.ended_at = utcnow()
    last = (await turns_of(db, session.id))[-1]
    last.events = [*last.events, *(event.model_dump(mode="json") for event in ended.events)]
    provider, config = request.app.state.llm
    session.debrief_status = "pending" if config is not None else "unavailable"
    session.turn_in_progress = None  # a stale turn's claim would make the finisher give up (and its write is refused)
    await db.commit()
    out = await session_out(db, session)
    await db.commit()  # close the reads before the background work below starts probing and writing
    if config is not None:
        request.app.state.background.spawn(
            finish_session(
                request.app.state.sessionmaker,
                Budgeted(
                    provider,
                    request.app.state.sessionmaker,
                    Actor(session.user_id, session.org_id, session.id, is_guest),
                    lambda: settings_of(request),
                ),
                config,
                session.id,
                content_of(request).rubric,
            )
        )
    return out


async def _open_session_for_closing(db: AsyncSession, context: OrgContext, session_id: uuid.UUID) -> PlaySession:
    session = await own_session(db, context, session_id, for_update=True)
    if session.status == Status.ended:
        raise Gone("This session has already ended")
    if session.turn_in_progress is not None and session.turn_in_progress > utcnow() - CLAIM_TIMEOUT:
        raise Conflict("A turn is still running; end the session after it")
    return session


@router.post("/{session_id}/end")
async def end_session(session_id: uuid.UUID, context: OrgDep, request: Request, db: Db) -> SessionOut:
    """The player stops. The debrief is written in the background; poll GET /debrief."""
    session = await _open_session_for_closing(db, context, session_id)
    return await close_session(request, db, session, end(State.model_validate(session.engine_state)), context.is_guest)


TIME_UP_SLACK = 1  # seconds: the clock rounds, and a browser's clock can run a moment behind


def clock_has_run_out(session: PlaySession, content: Mapping[str, Any]) -> bool:
    """Has the scenario's time run out, by the server's clock? False for a scenario that states no length."""
    _, seconds_left = seconds_left_of(session, content)
    return seconds_left is not None and seconds_left <= TIME_UP_SLACK


async def _time_is_up(db: AsyncSession, session: PlaySession) -> tuple[bool, str]:
    """(whether the scenario's minutes have run out and its rules end the meeting then, what it does)."""
    content = (await version_of(db, session)).content
    on_timeout = str((content.get("timing") or {}).get("on_timeout") or "guide")
    return on_timeout in ("end", "fail") and clock_has_run_out(session, content), on_timeout


@router.post("/{session_id}/time-up")
async def time_up_session(session_id: uuid.UUID, context: OrgDep, request: Request, db: Db) -> SessionOut:
    """The clock ran out in the player's browser. If the scenario's rules end the meeting then, and the server's own
    clock agrees, it ends now (as a failure or without a result); otherwise this is refused."""
    session = await _open_session_for_closing(db, context, session_id)
    up, on_timeout = await _time_is_up(db, session)
    if not up:
        raise Conflict("This session does not end on time, or there is time left")
    return await close_session(
        request,
        db,
        session,
        time_up(State.model_validate(session.engine_state), fail=on_timeout == "fail"),
        context.is_guest,
    )


async def _end_if_time_is_up(db: AsyncSession, context: OrgContext, request: Request, session_id: uuid.UUID) -> None:
    """Before a turn: a scenario whose rules end the meeting at the time limit does so, and the turn is refused."""
    session = await own_session(db, context, session_id)
    if session.status != Status.active or not (await _time_is_up(db, session))[0]:
        return
    await db.rollback()  # the read above ends here; the closing re-reads the row under its lock
    session = await _open_session_for_closing(db, context, session_id)
    up, on_timeout = await _time_is_up(db, session)
    if up:
        await close_session(
            request,
            db,
            session,
            time_up(State.model_validate(session.engine_state), fail=on_timeout == "fail"),
            context.is_guest,
        )
    else:
        await db.rollback()
        return
    raise Gone("Time is up: the meeting has ended")


def final_dials(state: State, scenario: EngineScenario) -> dict[str, int]:
    """What 'final dials' means when every party has its own entry: the single qualifying party's dials; otherwise
    the active party's, unless that is a stakeholder — then the primary counterpart's entry (a stakeholder's entry
    is a copied baseline plus small talk, never the negotiation's temperature)."""
    engaged = {pid for pid, count in state.stakeholder_engagements.items() if count > 0}
    qualifying = [pid for pid in state.counterpart_dials if not scenario.stakeholder_for(pid) or pid in engaged]
    if len(qualifying) == 1:
        return state.counterpart_dials[qualifying[0]]
    active = state.active_interlocutor
    if active and scenario.stakeholder_for(active):
        primary = scenario.counterparts[0].id if scenario.counterparts else None
        if primary and primary in state.counterpart_dials:
            return state.counterpart_dials[primary]
    return state.dials


@router.get("/{session_id}/debrief")
async def read_debrief(session_id: uuid.UUID, context: OrgDep, request: Request, db: Db) -> DebriefOut:
    """After the end only: outcome, milestones, the debrief, the final scores, the rule flags and the final dials.
    A debrief still pending five minutes after the end lost its finisher (a crash or restart) and is written again
    in the background."""
    session = await readable_session(db, context, session_id)
    if session.status != Status.ended:
        raise Conflict("The debrief comes after the session ends")
    state = State.model_validate(session.engine_state)
    turns = await turns_of(db, session_id)
    scored = [turn.scores for turn in turns if turn.scores is not None]
    content = (await version_of(db, session)).content  # the pinned version, as everywhere in the session
    cchn = compute_cchn_debrief(
        content=content,
        state=state,
        turns=turns,
        preparation=session.preparation,
        reflection=session.reflection,
        session_debrief=session.debrief,
    )
    party_dials: list[PartyDialsOut] | None = None
    engine_scenario = EngineScenario.from_content(content)
    if len(state.counterpart_dials) > 1:
        engaged = {pid for pid, count in state.stakeholder_engagements.items() if count > 0}
        parties = [(cp.id, cp.role, True) for cp in engine_scenario.counterparts] + [
            (str(sh.get("id") or ""), str(sh.get("role") or sh.get("id") or ""), False)
            for sh in engine_scenario.stakeholders
        ]
        rows = [
            PartyDialsOut(id=pid, role=role or pid, dials=state.counterpart_dials[pid])
            for pid, role, is_counterpart in parties
            if pid in state.counterpart_dials and (is_counterpart or pid in engaged)
        ]  # counterparts always; stakeholders only once actually engaged (never-engaged ones hold a copied baseline)
        party_dials = rows if len(rows) > 1 else None
    out = DebriefOut(
        status=session.debrief_status or "pending",
        outcome=state.outcome.model_dump(mode="json") if state.outcome else None,
        reached=[item.model_dump(mode="json") for item in state.reached],
        debrief=session.debrief,
        scores=scored[-1] if scored else None,
        flags=[flag.model_dump(mode="json") for flag in state.flags],
        dials=final_dials(state, engine_scenario),
        counterpart_dials=party_dials,
        hidden_facts=hidden_facts_of(content, Rules.model_validate(session.rules), state),
        dimensions=dimension_names(content_of(request).rubric, (content.get("rubric") or {}).get("dimensions") or []),
        dial_causes=dial_causes_of(turns, state),
        preparation=session.preparation,
        reflection=session.reflection,
        cchn_debrief=cchn,
        score_scale=(content.get("rubric") or {}).get("score_scale"),
    )
    if (
        session.debrief_status == "pending"
        and session.ended_at is not None
        and session.ended_at < utcnow() - DEBRIEF_RETRY_AFTER
    ):
        provider, config = request.app.state.llm
        if config is not None:
            await db.commit()  # close the reads before the background work starts
            request.app.state.background.spawn(
                finish_session(
                    request.app.state.sessionmaker,
                    Budgeted(
                        provider,
                        request.app.state.sessionmaker,
                        Actor(session.user_id, session.org_id, session.id, context.is_guest),
                        lambda: settings_of(request),
                    ),
                    config,
                    session.id,
                    content_of(request).rubric,
                )
            )
    return out


async def progress_out(db: AsyncSession, session: PlaySession) -> ProgressOut:
    player = await db.get_one(User, session.user_id)
    turns = await turns_of(db, session.id)
    scenario = await db.get_one(Scenario, session.scenario_id)
    content = (await version_of(db, session)).content  # the pinned version, not the scenario's current one
    phase_now = phase_at(content, State.model_validate(session.engine_state).turn)
    # Watchers steer, so every watcher sees the pinned twists and outcome rules — a member's private scenario
    # played in an org included; the invite notice says so.
    return ProgressOut(
        session_id=session.id,
        player=player.display_name,
        status=session.status,
        title=str(content.get("title") or scenario.title),
        state=session.engine_state,
        injections=[
            InjectionOut(id=str(item.get("id")), label=str(item.get("label") or item.get("id")))
            for item in content.get("injections") or []
        ],
        outcomes=[
            OutcomeOut(
                id=str(item.get("id")),
                label=str(item.get("label") or item.get("id")),
                result=str(item.get("result")),
                when=item.get("when") or {},
            )
            for item in content.get("outcomes") or []
        ],
        counterpart=str(content["counterparts"][0]["role"]),
        comments=[
            CommentOut(turn=row.turn, text=row.text, author=name, created_at=row.created_at)
            for row, name in await comments_of(db, session.id)
        ],
        turn_running=session.status == Status.active and session.turn_in_progress is not None,
        phase=phase_now.id,
        phase_label=phase_now.label,
        injects_allowed=phase_now.allow_injects,
        seconds_left=seconds_left_of(session, content)[1],
        on_timeout=(content.get("timing") or {}).get("on_timeout") or "guide",
        turns=[
            TurnProgress(
                number=turn.number,
                trainee_text=turn.trainee_text,
                reply_text=turn.reply_text,
                dials=turn.engine_state_after.get("dials", {}),
                events=turn.events,
                scores=turn.scores,
                counterpart_request=turn.counterpart_request,
            )
            for turn in turns
        ],
    )


@router.get("/{session_id}/progress")
async def watch(session_id: uuid.UUID, context: OrgDep, db: Db) -> ProgressOut:
    """Live progress: 404 for anyone who cannot read the session, 403 for the player of a solo session."""
    session = await readable_session(db, context, session_id)
    if not may_watch(session, context):
        raise Forbidden("Progress is hidden from the player until the session ends; read the debrief then")
    return await progress_out(db, session)


def ensure_injects_allowed(content: Mapping[str, Any], state: State) -> None:
    """A trainer's twist (preset or free text) is refused while the meeting is in a stage that forbids it."""
    stage = phase_at(content, state.turn)
    if not stage.allow_injects:
        raise Conflict(f"Twists are not allowed in the {stage.label} stage. Try again when it ends.")


@router.post("/{session_id}/inject")
async def twist(session_id: uuid.UUID, body: InjectIn, context: OrgDep, db: Db) -> ProgressOut:
    """A preset twist, by whoever may steer: the playtester in their own playtest, or an org admin in a member's
    solo session. The outcome is decided on the next trainee message."""
    session = await steerable_session(db, context, session_id, for_update=True)
    if not may_watch(session, context):
        raise Forbidden("Twists are for watchers; the player of a solo session never fires one")
    if session.status == Status.ended:
        raise Gone("This session has ended")
    if session.turn_in_progress is not None and session.turn_in_progress > utcnow() - CLAIM_TIMEOUT:
        raise Conflict("A turn is still running")
    content = (await version_of(db, session)).content
    state = State.model_validate(session.engine_state)
    ensure_injects_allowed(content, state)
    scenario = EngineScenario.from_content(content)
    twisted = inject(scenario, state, body.injection_id)
    session.engine_state = twisted.state.model_dump(mode="json")
    session.turn_in_progress = None  # a stale turn's claim is invalidated: its write can no longer erase the twist
    last = (await turns_of(db, session_id))[-1]
    last.events = [*last.events, *(event.model_dump(mode="json") for event in twisted.events)]
    await db.commit()
    return await progress_out(db, session)


@router.get("/{session_id}/coach/suggestions")
async def coach_suggestions(session_id: uuid.UUID, context: OrgDep, db: Db) -> CoachSuggestionsOut:
    """Provides tailored coach questions and relevant CCHN knowledge articles for this session."""
    session = await readable_session(db, context, session_id)
    content = (await version_of(db, session)).content
    state = State.model_validate(session.engine_state)
    counterpart = content.get("counterparts", [{}])[0].get("role", "the counterpart")

    kb = get_knowledge_base()
    recorded_moves = [move.id for move in state.moves]
    relevant_docs = kb.find_relevant(
        moves=recorded_moves,
        dials=list(state.dials.keys()),
        limit=3,
    )
    if not relevant_docs:
        relevant_docs = kb.all_docs()[:3]

    suggestions = [
        f"Why did {counterpart} resist my proposal?",
        "How could I have phrased my opening to build higher rapport?",
        f"What procedural constraints was {counterpart} protecting?",
        "Which CCHN tools should I apply to de-escalate tension next time?",
    ]
    citations = [
        CoachCitationOut(
            id=d.id,
            title=d.title,
            framework=d.framework,
            citation=d.citation,
            summary=d.summary,
        )
        for d in relevant_docs
    ]
    return CoachSuggestionsOut(suggestions=suggestions, citations=citations)


@router.post("/{session_id}/coach")
async def take_coach(
    session_id: uuid.UUID,
    body: CoachMessageIn,
    context: OrgDep,
    request: Request,
    db: Db,
) -> StreamingResponse:
    """Interactive debrief with an AI Coach grounded in CCHN frontline negotiation doctrine."""
    provider, config = budgeted_llm_of(request, Actor(context.user_id, context.org_id, session_id, context.is_guest))
    await check_limits(db, limits_of(settings_of(request)), context)
    session = await readable_session(db, context, session_id)
    if session.status != Status.ended:
        raise Conflict("The coach debrief comes after the session ends")
    cap = settings_of(request).coach_questions_per_session
    if cap:  # one atomic admission per question, whatever happens to the calls afterwards
        await admit(
            db,
            scope="coach_question",
            key=str(session.id),
            cap=cap,
            message="You have asked the coach as many questions as one session allows.",
            lifetime=True,  # the cap is per session, not per day: a session outlives midnight
        )
    await db.commit()  # the admission lands before the stream starts spending

    content = (await version_of(db, session)).content
    state = State.model_validate(session.engine_state)
    turns = await turns_of(db, session_id)
    trans = transcript(turns)
    debrief_summary = None
    if session.debrief and isinstance(session.debrief, dict):
        debrief_summary = session.debrief.get("summary")

    kb = get_knowledge_base()
    recorded_moves = [move.id for move in state.moves]
    relevant_docs = kb.find_relevant(
        query=body.question,
        moves=recorded_moves,
        dials=list(state.dials.keys()),
        limit=3,
    )
    if not relevant_docs:
        relevant_docs = kb.all_docs()[:3]

    app = request.app
    return TurnStream(
        _coach_turn(
            app.state.sessionmaker,
            provider,
            config,
            session.id,
            context.user_id,  # the caller that was checked is the caller that is billed
            context.org_id,
            content,
            str(content.get("title") or "Simulation"),
            state.outcome.model_dump(mode="json") if state.outcome else None,
            final_dials(state, EngineScenario.from_content(content)),
            debrief_summary,
            trans,
            relevant_docs,
            body.history,
            body.question,
            session.preparation,
            session.reflection,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _coach_turn(
    maker: Any,
    provider: Provider,
    config: LLMConfig,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    content: Mapping[str, Any],
    session_title: str,
    outcome: Mapping[str, Any] | None,
    dials: Mapping[str, Any],
    debrief_summary: str | None,
    trans: list[Line],
    relevant_docs: list[Any],
    history: list[dict[str, str]],
    question: str,
    preparation: Mapping[str, Any] | None = None,
    reflection: Mapping[str, Any] | None = None,
) -> AsyncIterator[bytes]:
    db = maker()
    try:
        # First a small check that the question is about the session and negotiation practice: an off-topic one is
        # answered with a fixed line and never reaches the coach's model. If the check cannot run, nothing is answered.
        ids = {"user_id": user_id, "org_id": org_id, "session_id": session_id}
        try:
            scope = await coach_scope(provider, config, session_title, history, question)
        except (AdmissionDenied, InputTooLarge) as exc:  # refused before the provider call: nothing is billed
            yield sse("error", {"detail": str(exc)})
            return
        except MalformedAnswer as exc:
            record_call(db, exc.record, **ids)
            await db.commit()
            yield sse("error", {"detail": "The coach could not check your question. Please ask again."})
            return
        except CallFailed as exc:  # a paid partial failure: its usage and attempts reach the ledger
            logger.warning("Coach scope check failed (%s)", type(exc.__cause__ or exc).__name__)
            record_call(db, exc.record, **ids)
            await db.commit()
            yield sse("error", {"detail": "The coach could not check your question. Please ask again."})
            return
        except Exception as exc:
            logger.warning("Coach scope check failed (%s)", type(exc).__name__)
            record_error(db, "scope", config.for_role("scope").model, **ids)
            await db.commit()
            yield sse("error", {"detail": "The coach could not check your question. Please ask again."})
            return
        record_call(db, scope.record, **ids)
        await db.commit()
        if not scope.value.on_topic:
            yield sse("reply", {"text": coach_refusal()})
            yield sse("done", {"citations": []})
            return
        citations = [
            {
                "id": doc.id,
                "title": doc.title,
                "framework": doc.framework,
                "citation": doc.citation,
                "summary": doc.summary,
            }
            for doc in relevant_docs
        ]
        yield sse("citations", {"items": citations})

        req = coach_request(
            config=config,
            content=content,
            session_title=session_title,
            outcome=outcome,
            dials=dials,
            debrief_summary=debrief_summary,
            transcript=trans,
            relevant_docs=relevant_docs,
            history=history,
            question=question,
            preparation=preparation,
            reflection=reflection,
        )
        stream = CoachStream(provider, config.for_role("coach"), req)
        async for chunk in stream:
            yield sse("reply", {"text": chunk})

        if stream.record is not None:
            record_call(db, stream.record, user_id=user_id, org_id=org_id, session_id=session_id)
            await db.commit()

        yield sse("done", {"citations": citations})
    except (AdmissionDenied, InputTooLarge) as exc:  # refused before the provider call: nothing is billed
        yield sse("error", {"detail": str(exc)})
    except Exception as exc:
        logger.warning("Coach stream failed (%s)", type(exc).__name__)
        try:
            record_error(
                db, "coach", config.for_role("coach").model, user_id=user_id, org_id=org_id, session_id=session_id
            )
            await db.commit()
        except Exception as exc:
            logger.warning("Failed to record coach error in ledger (%s)", type(exc).__name__)
        yield sse("error", {"detail": "The coach could not complete the response. Please ask again."})
    finally:
        await db.close()
