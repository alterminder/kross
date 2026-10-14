"""Retention purge: ended-long-ago and truly abandoned sessions go (turns cascade); the ledger always stays."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from nlab.api.purge import purge
from nlab.db.auth_sessions import utcnow
from nlab.db.models import LlmCall, PlaySession, Status, Turn
from nlab.db.sessions import CLAIM_TIMEOUT, purge_sessions
from tests.api.support import card_id, count, say, seed_curated, sign_in, start_play, use_model
from tests.api.test_limits import spend

pytestmark = pytest.mark.anyio


async def backdate(app, values, *session_ids, turns_too=False):
    """Sets PlaySession columns (and, with turns_too, the turns' created_at) for the given sessions."""
    ids = [uuid.UUID(item) for item in session_ids]
    async with app.state.sessionmaker() as db:
        await db.execute(update(PlaySession).where(PlaySession.id.in_(ids)).values(**values))
        if turns_too and "created_at" in values:
            await db.execute(update(Turn).where(Turn.session_id.in_(ids)).values(created_at=values["created_at"]))
        await db.commit()


async def test_old_sessions_go_and_recent_ones_and_the_ledger_stay(app, new_client):
    await seed_curated(app)
    alice = new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    scenario_id = await card_id(alice, "camp")
    old_ended, old_active, recent = [(await start_play(alice, scenario_id))["id"] for _ in range(3)]
    long_ago = utcnow() - timedelta(days=40)
    await backdate(app, {"status": Status.ended, "ended_at": long_ago}, old_ended, turns_too=True)
    await backdate(app, {"created_at": long_ago}, old_active, turns_too=True)
    await spend(app, me, tokens_in=5)  # an unlinked ledger row
    async with app.state.sessionmaker() as db:
        db.add(  # a ledger row linked to the session that will be purged
            LlmCall(
                user_id=me["id"],
                org_id=me["active_org"]["id"],
                session_id=uuid.UUID(old_ended),
                role="classifier",
                model="test-model",
                outcome="ok",
            )
        )
        await db.commit()
        assert await purge_sessions(db, days=30) == 2
        await db.commit()
        left = set(await db.scalars(select(PlaySession.id)))
        remaining_turn_sessions = set(await db.scalars(select(Turn.session_id)))
    assert {str(item) for item in left} == {recent}
    assert remaining_turn_sessions == {uuid.UUID(recent)}  # the purged sessions' turns cascaded away
    assert await count(app, LlmCall) == 2  # both ledger rows stay, including the purged session's


async def test_a_recently_played_old_session_survives(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    use_model(app)
    session = await start_play(alice, await card_id(alice, "camp"))
    long_ago = utcnow() - timedelta(days=40)
    await backdate(app, {"created_at": long_ago}, session["id"], turns_too=True)
    events = await asyncio.wait_for(say(alice, session["id"], "Hello."), timeout=10)  # resumed now: a fresh turn
    assert any(event == "done" for event, _ in events)
    await app.state.background.drain(timeout=10)
    async with app.state.sessionmaker() as db:
        latest = await db.scalar(select(Turn).where(Turn.session_id == session["id"], Turn.number == 1))
        assert latest.created_at > utcnow() - timedelta(minutes=1)
        assert await purge_sessions(db, days=30) == 0
        await db.commit()


async def test_a_claim_inside_the_window_protects_an_old_session(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    scenario_id = await card_id(alice, "camp")
    claimed, long_turn, stale = [(await start_play(alice, scenario_id))["id"] for _ in range(3)]
    long_ago = utcnow() - timedelta(days=40)
    await backdate(app, {"created_at": long_ago}, claimed, long_turn, stale, turns_too=True)
    await backdate(app, {"turn_in_progress": utcnow()}, claimed)  # a turn is running right now
    # a turn running 10 minutes: older than CLAIM_TIMEOUT (a takeover bound), but inside the retention window
    await backdate(app, {"turn_in_progress": utcnow() - timedelta(minutes=10)}, long_turn)
    assert timedelta(minutes=10) > CLAIM_TIMEOUT
    await backdate(app, {"turn_in_progress": utcnow() - timedelta(days=31)}, stale)  # abandoned before the cutoff
    async with app.state.sessionmaker() as db:
        assert await purge_sessions(db, days=30) == 1
        await db.commit()
        left = {str(item) for item in await db.scalars(select(PlaySession.id))}
    assert left == {claimed, long_turn}


async def test_a_turn_in_flight_protects_its_session_from_the_purge(app, new_client):
    """The reviewer's E3a: purge runs while a resumed old session's turn is in flight and must delete nothing."""
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    model = use_model(app)
    session = await start_play(alice, await card_id(alice, "camp"))
    await backdate(app, {"created_at": utcnow() - timedelta(days=40)}, session["id"], turns_too=True)
    gate = asyncio.Event()
    model.gates["classifier"] = gate  # the classifier answers only once the test opens the gate
    streamed = asyncio.create_task(say(alice, session["id"], "Hello."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)  # the turn holds its claim now
    async with app.state.sessionmaker() as db:
        assert await asyncio.wait_for(purge_sessions(db, days=30), timeout=10) == 0
        await db.commit()
    gate.set()
    events = await asyncio.wait_for(streamed, timeout=10)
    assert any(event == "done" for event, _ in events)
    await app.state.background.drain(timeout=10)
    assert await count(app, PlaySession) == 1


async def test_an_old_session_that_ended_recently_survives(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    await backdate(
        app,
        {"created_at": utcnow() - timedelta(days=40), "status": Status.ended, "ended_at": utcnow()},
        session["id"],
        turns_too=True,
    )
    async with app.state.sessionmaker() as db:
        assert await purge_sessions(db, days=30) == 0
        await db.commit()


async def test_the_cutoff_is_exact(app, new_client):
    """Strictly older than the cutoff goes; at or after it stays, for ended and abandoned sessions alike."""
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    scenario_id = await card_id(alice, "camp")
    ended_before, ended_at_edge, made_before, made_at_edge = [
        (await start_play(alice, scenario_id))["id"] for _ in range(4)
    ]
    cutoff = utcnow() - timedelta(days=30)
    margin = timedelta(minutes=2)  # wide enough that the purge's own utcnow() cannot cross it
    await backdate(app, {"status": Status.ended, "ended_at": cutoff - margin}, ended_before, turns_too=True)
    await backdate(app, {"status": Status.ended, "ended_at": cutoff + margin}, ended_at_edge, turns_too=True)
    await backdate(app, {"created_at": cutoff - margin}, made_before, turns_too=True)
    await backdate(app, {"created_at": cutoff + margin}, made_at_edge, turns_too=True)
    async with app.state.sessionmaker() as db:
        assert await purge_sessions(db, days=30) == 2
        await db.commit()
        left = {str(item) for item in await db.scalars(select(PlaySession.id))}
    assert left == {ended_at_edge, made_at_edge}


async def test_the_purge_command_is_off_by_default_and_deletes_when_on(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    long_ago = utcnow() - timedelta(days=40)
    await backdate(app, {"status": Status.ended, "ended_at": long_ago}, session["id"], turns_too=True)
    assert await purge(app.state.settings) == (0, 0)  # session_retention_days defaults to 0: keep forever
    assert await count(app, PlaySession) == 1
    on = app.state.settings.model_copy(update={"session_retention_days": 30})
    assert await asyncio.wait_for(purge(on), timeout=10) == (1, 0)
    assert await count(app, PlaySession) == 0


async def test_scheduled_purge_removes_expired_and_idle_auth_sessions(app, new_client):
    from nlab.api.deps import COOKIE
    from nlab.db.auth_sessions import hash_token
    from nlab.db.models import AuthSession

    browsers = [new_client() for _ in range(3)]
    for client in browsers:
        await sign_in(client, "alice", "alice@example.org")
    hashes = [hash_token(client.cookies[COOKIE]) for client in browsers]
    async with app.state.sessionmaker() as db:
        await db.execute(
            update(AuthSession).where(AuthSession.id_hash == hashes[0]).values(expires_at=utcnow() - timedelta(hours=1))
        )
        await db.execute(
            update(AuthSession)
            .where(AuthSession.id_hash == hashes[1])
            .values(last_seen_at=utcnow() - timedelta(hours=9))
        )
        await db.commit()
    assert await purge(app.state.settings) == (0, 0)
    async with app.state.sessionmaker() as db:
        assert set(await db.scalars(select(AuthSession.id_hash))) == {hashes[2]}
