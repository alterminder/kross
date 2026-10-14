import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from nlab.db.models import PlaySession
from tests.api.support import draft, join, org_with_admin, say, sign_in, start_play, use_model

pytestmark = pytest.mark.anyio


async def test_a_playtester_sees_progress_and_fires_twists(app, new_client):
    use_model(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    session = await start_play(alice, mine["id"], "playtest")
    await say(alice, session["id"], "Hello.")
    progress = await alice.get(f"/api/sessions/{session['id']}/progress")
    assert progress.status_code == 200
    twisted = await alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    assert twisted.status_code == 200
    assert "military_call" in {item["id"] for item in twisted.json()["state"]["injections"]}
    assert twisted.json()["state"]["outcome"] is None  # a twist never ends the session by itself
    unknown = await alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "no_such_twist"})
    assert unknown.status_code == 422


async def test_playtest_twists_come_from_the_pinned_version(app, new_client):
    """Editing the scenario after a playtest started never changes the twists the panel offers or fires."""
    use_model(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    session = await start_play(alice, mine["id"], "playtest")
    changed = draft()
    changed["injections"] = [{"id": "new_twist", "label": "A new twist", "instruction": "Mention a new twist."}]
    assert (await alice.put(f"/api/scenarios/{mine['id']}", json={"content": changed})).status_code == 200
    progress = (await alice.get(f"/api/sessions/{session['id']}/progress")).json()
    first = [(item["id"], item["label"]) for item in progress["injections"][0:1]]
    assert first == [("military_call", "Military objects")]
    assert "new_twist" not in {item["id"] for item in progress["injections"]}
    twisted = await alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    assert twisted.status_code == 200
    unknown = await alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "new_twist"})
    assert unknown.status_code == 422


async def test_twists_are_for_playtests_only_and_admins_do_not_watch_playtests(app, new_client):
    use_model(app)
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    mine = (await bob.post("/api/scenarios", json={"content": draft()})).json()
    solo = await start_play(bob, mine["id"])
    assert (
        await bob.post(f"/api/sessions/{solo['id']}/inject", json={"injection_id": "military_call"})
    ).status_code == 403
    playtest = await start_play(bob, mine["id"], "playtest")
    assert (await admin.get(f"/api/sessions/{playtest['id']}/progress")).status_code == 404
    assert playtest["id"] not in {item["id"] for item in (await admin.get("/api/sessions?scope=org")).json()}


async def test_an_inject_waits_for_the_sessions_row_lock(app, new_client):
    """/inject serialises on the session row, as /end and the turn commit do: while another writer holds the row,
    the twist waits instead of racing it."""
    use_model(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    session = await start_play(alice, mine["id"], "playtest")
    async with app.state.sessionmaker() as db:  # hold the session row, as a committing turn or end does
        await db.execute(select(PlaySession.id).where(PlaySession.id == session["id"]).with_for_update())
        twist = asyncio.create_task(
            alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
        )
        await asyncio.sleep(0.3)
        assert not twist.done()  # the twist is waiting for the row lock
        await db.commit()
    assert (await asyncio.wait_for(twist, timeout=10)).status_code == 200


async def test_an_inject_over_a_committing_turn_reads_the_state_after_the_turn(app, new_client):
    """A twist fired while a turn's final write waits on the session row lock queues behind that write and reads
    the state after it: the turn's claim is already cleared, so the twist applies to the new state. Without the
    FOR UPDATE read the twist would see the stale pre-turn state and refuse (or erase the turn's write)."""
    model = use_model(app)
    gate = model.once["classifier"] = asyncio.Event()
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    session = await start_play(alice, mine["id"], "playtest")
    turn = asyncio.create_task(say(alice, session["id"], "A message."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)  # the turn holds its claim
    async with app.state.sessionmaker() as db:  # hold the session row, so the turn's final write queues for it
        await db.execute(select(PlaySession.id).where(PlaySession.id == session["id"]).with_for_update())
        gate.set()
        await asyncio.sleep(0.3)  # the turn finishes its model calls and queues its final write on the row
        twist = asyncio.create_task(
            alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
        )
        await asyncio.sleep(0.3)  # the twist queues behind the turn's write (or, unlocked, reads the stale state)
        await db.commit()
    events, twisted = await asyncio.wait_for(asyncio.gather(turn, twist), timeout=10)
    assert events[-1][0] == "done"  # the turn won the row and saved
    assert twisted.status_code == 200
    state = twisted.json()["state"]
    assert state["turn"] == 1  # the twist read the state after the turn, not the stale pre-turn state
    assert "military_call" in {item["id"] for item in state["injections"]}


async def test_an_inject_erases_a_stale_turns_claim(app, new_client, monkeypatch):
    """A twist over a stale but live turn clears the claim: the turn's write is refused and the twist survives."""
    import nlab.api.play as play

    model = use_model(app)
    gate = model.once["classifier"] = asyncio.Event()
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    session = await start_play(alice, mine["id"], "playtest")
    turn = asyncio.create_task(say(alice, session["id"], "A message."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)
    real = play.utcnow
    monkeypatch.setattr(play, "utcnow", lambda: real() + timedelta(minutes=4))  # /inject sees the claim 4 min old
    twisted = await alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    monkeypatch.setattr(play, "utcnow", real)
    assert twisted.status_code == 200
    gate.set()
    events = await asyncio.wait_for(turn, timeout=10)
    assert events[-1] == ("error", {"detail": "The session changed while the model was working; nothing was saved."})
    progress = (await alice.get(f"/api/sessions/{session['id']}/progress")).json()
    assert any(item["id"] == "military_call" for item in progress["state"]["injections"])  # the twist survives
