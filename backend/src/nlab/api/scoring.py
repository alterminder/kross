"""Background scoring and debriefs, each in its own database session. Failures are logged, never raised: the
player's turn is already saved."""

import asyncio
import logging
import time
import uuid
from typing import Any

import anyio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nlab.db.auth_sessions import utcnow
from nlab.db.ledger import record_call, record_error
from nlab.db.models import PlaySession
from nlab.db.sessions import (
    SCORING_TIMEOUT,
    claim_finish,
    claim_scoring,
    release_turn,
    transcript,
    turns_of,
    version_of,
)
from nlab.engine import Rubric, State
from nlab.llm import (
    CallFailed,
    LLMConfig,
    MalformedAnswer,
    Provider,
    ScoreCheck,
    TurnScores,
    compare_scores,
    debrief,
    evaluate,
)
from nlab.llm.types import AdmissionDenied, InputTooLarge

logger = logging.getLogger(__name__)
Maker = async_sessionmaker[AsyncSession]
WAIT_FOR_SCORERS_SECONDS = 90
SECOND_PASS_TEMPERATURE = 0.7  # the check is a real second sample, not a repeat of the first (which runs at 0)


def _definitions(rubric: Rubric | None, content: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    return rubric.definitions((content.get("rubric") or {}).get("dimensions") or []) if rubric else None


async def score_turn(
    maker: Maker,
    provider: Provider,
    config: LLMConfig,
    session_id: uuid.UUID,
    number: int,
    rubric: Rubric | None = None,
) -> None:
    """Scores turn `number` over the transcript up to it. Skips a turn someone else is already scoring. `rubric` is
    the shared rubric, whose look-for text and CCHN tools the evaluator reads."""
    async with maker() as db:
        session = await db.get_one(PlaySession, session_id)
        turns = await turns_of(db, session_id)
        turn = next((item for item in turns if item.number == number), None)
        if turn is None or number < 1 or not await claim_scoring(db, turn.id):
            return
        await db.commit()
        ids = {"user_id": session.user_id, "org_id": session.org_id, "session_id": session.id}
        content = (await version_of(db, session)).content
        upto = [item for item in turns if item.number <= number]
        state_after = State.model_validate(turn.engine_state_after)
        await db.commit()  # the read transaction ends here: no transaction is open during the model call
        try:
            result = await evaluate(
                provider, config, content, state_after, transcript(upto), definitions=_definitions(rubric, content)
            )
        except (AdmissionDenied, InputTooLarge):  # refused before the call: skip this paid scoring, charge nothing
            turn.scoring_started_at = None
            await db.commit()
            return
        except MalformedAnswer as exc:
            logger.warning("Scoring turn %s of session %s unusable: %s", number, session_id, exc)
            record_call(db, exc.record, **ids)
            turn.scoring_started_at = None  # let the session end try again
            await db.commit()
            return
        except CallFailed as exc:  # a paid partial failure: its usage and attempts reach the ledger
            logger.warning(
                "Scoring turn %s of session %s failed (%s)", number, session_id, type(exc.__cause__ or exc).__name__
            )
            record_call(db, exc.record, **ids)
            turn.scoring_started_at = None
            await db.commit()
            return
        except Exception as exc:
            logger.warning("Scoring turn %s of session %s failed (%s)", number, session_id, type(exc).__name__)
            record_error(db, "evaluator", config.for_role("evaluator").model, **ids)
            turn.scoring_started_at = None
            await db.commit()
            return
        turn.scores = result.value.model_dump(mode="json")
        record_call(db, result.record, **ids)
        await db.commit()


async def finish_session(
    maker: Maker, provider: Provider, config: LLMConfig, session_id: uuid.UUID, rubric: Rubric | None = None
) -> None:
    """After the end: score every still-unscored turn, wait (bounded) for scorers still running, write the debrief.
    One finisher per session: a second spawn (a double end, a poll) does nothing. Any exit other than success leaves
    debrief_status 'failed' in a shielded write, so an interrupted debrief is never stuck at 'pending'."""
    outcome = "failed"
    try:
        outcome = await _finish(maker, provider, config, session_id, rubric)
    finally:
        if outcome == "failed":
            with anyio.CancelScope(shield=True):
                await _mark_failed(maker, session_id)


async def _finish(
    maker: Maker, provider: Provider, config: LLMConfig, session_id: uuid.UUID, rubric: Rubric | None
) -> str:
    """'ready' when the debrief was written, 'not_mine' when another finisher owns the session, 'failed' otherwise."""
    async with maker() as db:
        token = await claim_finish(db, session_id)
        if token is None:
            return "not_mine"
        numbers = [turn.number for turn in await turns_of(db, session_id) if turn.number >= 1 and turn.scores is None]
        await db.commit()  # the finish claim must survive; no transaction is held over the work below
    for number in numbers:
        await score_turn(maker, provider, config, session_id, number, rubric)
    deadline = time.monotonic() + WAIT_FOR_SCORERS_SECONDS
    while time.monotonic() < deadline:
        async with maker() as db:
            running = [
                turn
                for turn in await turns_of(db, session_id)
                if turn.scores is None
                and turn.scoring_started_at is not None
                and turn.scoring_started_at > utcnow() - SCORING_TIMEOUT
            ]
        if not running:
            break
        await asyncio.sleep(0.5)
    async with maker() as db:
        session = await db.get_one(PlaySession, session_id)
        turns = await turns_of(db, session_id)
        ids = {"user_id": session.user_id, "org_id": session.org_id, "session_id": session.id}
        scores = [TurnScores(turn=turn.number, **turn.scores) for turn in turns if turn.scores is not None]
        content = (await version_of(db, session)).content
        state = State.model_validate(session.engine_state)
        await db.commit()
        lines = transcript(turns)
        checks: list[ScoreCheck] = []
        if scores:  # a second opinion on the whole transcript; a failure only means the scores carry no check
            try:
                second = await evaluate(
                    provider,
                    config,
                    content,
                    state,
                    lines,
                    temperature=SECOND_PASS_TEMPERATURE,
                    definitions=_definitions(rubric, content),
                )
            except (AdmissionDenied, InputTooLarge):  # the second opinion is optional: skip it without a charge
                pass
            except MalformedAnswer as exc:
                record_call(db, exc.record, **ids)
            except CallFailed as exc:
                logger.warning(
                    "Second scoring pass of session %s failed (%s)", session_id, type(exc.__cause__ or exc).__name__
                )
                record_call(db, exc.record, **ids)
            except Exception as exc:
                logger.warning("Second scoring pass of session %s failed (%s)", session_id, type(exc).__name__)
                record_error(db, "evaluator", config.for_role("evaluator").model, **ids)
            else:
                record_call(db, second.record, **ids)
                checks = compare_scores(scores[-1], second.value)  # the last scored turn's pass covers it all
            await db.commit()
        outcome = "failed"
        try:
            result = await debrief(provider, config, content, state, scores, lines)
        except (AdmissionDenied, InputTooLarge):  # refused before the call: no paid work after exhaustion
            outcome = "failed"  # the end stays 200 and the status says the debrief was skipped
            await release_turn(db, session_id, token)
        except MalformedAnswer as exc:
            logger.warning("Debrief of session %s unusable: %s", session_id, exc)
            record_call(db, exc.record, **ids)
            await release_turn(db, session_id, token)
        except CallFailed as exc:
            logger.warning("Debrief of session %s failed (%s)", session_id, type(exc.__cause__ or exc).__name__)
            record_call(db, exc.record, **ids)
            await release_turn(db, session_id, token)
        except Exception as exc:
            logger.warning("Debrief of session %s failed (%s)", session_id, type(exc).__name__)
            record_error(db, "debrief", config.for_role("debrief").model, **ids)
            await release_turn(db, session_id, token)
        else:
            record_call(db, result.record, **ids)
            # only the finisher still holding the slot writes the debrief: a slower finisher whose slot was taken
            # over must not overwrite the winner's, and the write frees the slot itself
            won = await db.scalar(
                update(PlaySession)
                .where(PlaySession.id == session_id, PlaySession.turn_in_progress == token)
                .values(
                    debrief={**result.value.model_dump(mode="json"), "score_check": [c.model_dump() for c in checks]},
                    debrief_status="ready",
                    turn_in_progress=None,
                )
                .returning(PlaySession.id)
            )
            outcome = "ready" if won is not None else "not_mine"
        await db.commit()
        return outcome


async def _mark_failed(maker: Maker, session_id: uuid.UUID) -> None:
    """The last word of a finisher that did not succeed: 'failed' over 'pending' only, so it never overwrites a
    'ready' another finisher wrote."""
    db = maker()
    try:
        await db.execute(
            update(PlaySession)
            .where(PlaySession.id == session_id, PlaySession.debrief_status == "pending")
            .values(debrief_status="failed")
        )
        await db.commit()
    except Exception as exc:
        logger.warning("Marking the debrief of session %s failed did not work (%s)", session_id, type(exc).__name__)
        await db.rollback()
    finally:
        await db.close()
