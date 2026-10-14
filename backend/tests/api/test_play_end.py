import asyncio
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from nlab.api.scoring import finish_session
from nlab.db.auth_sessions import utcnow
from nlab.db.models import PlaySession, Turn
from tests.api.support import (
    PLAY_CONFIG,
    card_id,
    done_of,
    ledger,
    nudge,
    say,
    seed_curated,
    settle,
    sign_in,
    start_play,
    use_model,
)

pytestmark = pytest.mark.anyio


async def playing(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    return alice, await start_play(alice, await card_id(alice, "camp"))


async def stored_row(app, session_id):
    async with app.state.sessionmaker() as db:
        return await db.get_one(PlaySession, session_id)


async def test_the_debrief_comes_only_after_the_end(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "What worries you most?")
    assert (await alice.get(f"/api/sessions/{session['id']}/debrief")).status_code == 409
    ended = await alice.post(f"/api/sessions/{session['id']}/end")
    assert ended.status_code == 200 and ended.json()["status"] == "ended"
    assert ended.json()["outcome"]["result"] == "ended"
    await settle(app)
    debrief = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert debrief["status"] == "ready" and debrief["debrief"]["summary"] == "A short debrief."
    assert debrief["outcome"]["result"] == "ended" and "trust" in debrief["dials"]
    assert ("debrief", "ok") in await ledger(app, session["id"])


async def test_an_unscored_turn_is_scored_at_the_end(app, new_client):
    model = use_model(app)
    model.answers["evaluator"].extend(["not json", "not json"])  # the background scoring of turn 1 fails
    score = json.dumps({"scores": [{"id": "questioning", "score": 4, "quote": "What worries you"}]})
    model.answers["evaluator"].append(score)  # the end's retry succeeds
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "What worries you most?")
    await settle(app)
    async with app.state.sessionmaker() as db:
        assert await db.scalar(select(Turn.scores).where(Turn.number == 1)) is None
    await alice.post(f"/api/sessions/{session['id']}/end")
    await settle(app)
    debrief = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert debrief["status"] == "ready"
    assert debrief["scores"]["scores"] == [{"id": "questioning", "score": 4, "quote": "What worries you"}]


async def test_ending_twice_is_gone_and_a_running_turn_blocks_the_end(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client)
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 410


async def test_without_a_model_the_debrief_is_unavailable(app, new_client):
    alice, session = await playing(app, new_client)  # the default app has no model configured
    await alice.post(f"/api/sessions/{session['id']}/end")
    await settle(app)
    assert (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()["status"] == "unavailable"


async def test_a_session_that_ends_on_a_turn_gets_its_debrief(app, new_client):
    model = use_model(app)
    alice, session = await playing(app, new_client)
    model.answers["classifier"].append(json.dumps({"moves": [{"id": "insults_counterpart", "quote": "idiot"}]}))
    await say(alice, session["id"], "You idiot.")
    assert model.calls["counterpart"] == 0  # the plan's no-reply rule: an insult gets no closing line
    await settle(app)
    async with app.state.sessionmaker() as db:
        row = await db.get_one(PlaySession, session["id"])
    assert row.status == "ended" and row.debrief_status == "ready"


async def test_two_ends_at_once_let_exactly_one_through(app, new_client):
    """Two POST /end racing (E3b): one 200 and one 410, and exactly one finisher writes the debrief."""
    model = use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    camp = await card_id(alice, "camp")
    for _ in range(3):
        session = await start_play(alice, camp)
        url = f"/api/sessions/{session['id']}/end"
        first, second = await asyncio.wait_for(asyncio.gather(alice.post(url), alice.post(url)), timeout=10)
        assert sorted((first.status_code, second.status_code)) == [200, 410]
    await settle(app)
    assert model.calls["debrief"] == 3  # one debrief per session, never two finishers


async def test_an_end_racing_a_turn_never_loses_the_outcome(app, new_client):
    """POST /end and a turn at once (E4b): whatever interleaving happens, an ended session always carries its
    outcome, and no claim is left behind."""
    use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    camp = await card_id(alice, "camp")
    for _ in range(4):
        session = await start_play(alice, camp)
        sid = session["id"]
        await asyncio.wait_for(
            asyncio.gather(
                alice.post(f"/api/sessions/{sid}/end"),
                say(alice, sid, "Hello."),
                return_exceptions=True,
            ),
            timeout=20,
        )
        await settle(app)
        row = await stored_row(app, sid)
        assert row.turn_in_progress is None
        assert row.status != "ended" or row.engine_state["outcome"] is not None


async def test_scoring_provider_errors_stay_on_the_ledger(app, new_client):
    model = use_model(app)
    model.answers["evaluator"].append(RuntimeError("provider 500"))
    model.answers["debrief"].append(RuntimeError("provider 500"))
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "What worries you most?")
    await settle(app)
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await settle(app)
    rows = await ledger(app, session["id"])
    assert ("evaluator", "error") in rows and ("debrief", "error") in rows
    assert ("evaluator", "ok") in rows  # the end's retry scores the turn


async def test_a_failed_debrief_is_marked_failed(app, new_client):
    model = use_model(app)
    model.answers["debrief"].extend(["not json", "not json"])
    alice, session = await playing(app, new_client)
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await settle(app)
    debrief = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert debrief["status"] == "failed"
    assert ("debrief", "malformed") in await ledger(app, session["id"])


async def test_a_debrief_cancelled_by_shutdown_is_failed_not_pending(app, new_client):
    """E9: the debrief model hangs and shutdown cancels the finisher; the player must see 'failed', never a
    'pending' that nothing will ever finish."""
    model = use_model(app)
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "Hello.")
    await settle(app)
    model.hang.add("debrief")
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(app.state.background.drain(timeout=1), timeout=15)
    status = None
    for _ in range(20):  # the shielded write lands as the cancelled task finishes; the wait is bounded
        status = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()["status"]
        if status != "pending":
            break
        await asyncio.sleep(0.1)
    assert status == "failed"


async def test_a_stuck_pending_debrief_is_retried_when_polled(app, new_client):
    """A crash after the end can leave the debrief pending with a dead finisher; polling past five minutes writes
    it again."""
    use_model(app)
    alice, session = await playing(app, new_client)
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await settle(app)
    async with app.state.sessionmaker() as db:
        row = await db.get_one(PlaySession, session["id"])
        row.debrief = None
        row.debrief_status = "pending"
        row.ended_at = utcnow() - timedelta(minutes=10)
        row.turn_in_progress = utcnow() - timedelta(minutes=10)  # the dead finisher's stale claim
        await db.commit()
    assert (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()["status"] == "pending"
    await settle(app)
    debrief = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert debrief["status"] == "ready" and debrief["debrief"]["summary"] == "A short debrief."


async def test_an_end_over_a_stale_turn_starts_the_debrief(app, new_client, monkeypatch):
    """E4r: /end over a stale but live turn clears the claim so the finisher runs, and the stale turn's write is
    refused, keeping /end's outcome."""
    import nlab.api.play as play

    model = use_model(app)
    gate = model.once["classifier"] = asyncio.Event()
    alice, session = await playing(app, new_client)
    turn = asyncio.create_task(say(alice, session["id"], "Hello."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)
    real = play.utcnow
    monkeypatch.setattr(play, "utcnow", lambda: real() + timedelta(minutes=4))  # /end sees the claim 4 min old
    ended = await alice.post(f"/api/sessions/{session['id']}/end")
    monkeypatch.setattr(play, "utcnow", real)
    assert ended.status_code == 200
    gate.set()
    events = await asyncio.wait_for(turn, timeout=10)
    assert events[-1] == ("error", {"detail": "The session changed while the model was working; nothing was saved."})
    await settle(app)
    stored = await stored_row(app, session["id"])
    assert stored.engine_state["outcome"] is not None  # /end's outcome survives the stale turn
    assert stored.turn_in_progress is None
    debrief = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert debrief["status"] == "ready" and model.calls["debrief"] == 1  # the stale claim must not stop the finisher


async def test_a_running_turn_blocks_the_end(app, new_client):
    """A real running turn (a gated classifier) makes POST /end answer 409."""
    model = use_model(app)
    gate = model.once["classifier"] = asyncio.Event()
    alice, session = await playing(app, new_client)
    turn = asyncio.create_task(say(alice, session["id"], "Hello."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 409
    gate.set()
    assert done_of(await asyncio.wait_for(turn, timeout=10))["turn"] == 1


async def test_an_ended_session_refuses_new_turns(app, new_client):
    model = use_model(app)
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "Hello.")
    await settle(app)
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await settle(app)  # the finisher is done and has released the finish slot
    calls = model.calls["classifier"]
    refused = await asyncio.wait_for(alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Again."}), 10)
    assert refused.status_code == 410
    assert model.calls["classifier"] == calls  # the refusal happens before any model call


async def test_only_one_finisher_writes_the_debrief(app, new_client):
    model = use_model(app)
    model.gates["debrief"] = asyncio.Event()
    alice, session = await playing(app, new_client)
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await asyncio.wait_for(model.entered["debrief"].wait(), timeout=10)  # the first finisher holds the finish slot
    app.state.background.spawn(finish_session(app.state.sessionmaker, model, PLAY_CONFIG, session["id"]))
    await asyncio.sleep(0.2)  # a second finisher without the claim would call the debrief before this line
    model.gates["debrief"].set()
    await settle(app)
    assert model.calls["debrief"] == 1


async def test_the_finisher_waits_for_a_running_scorer_and_never_doubles_it(app, new_client):
    model = use_model(app)
    gate = model.gates["evaluator"] = asyncio.Event()
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "What worries you most?")
    await asyncio.wait_for(model.entered["evaluator"].wait(), timeout=10)  # the turn's scorer is inside its call
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await asyncio.sleep(0.5)  # a finisher that does not wait writes its debrief before this line
    gate.set()
    await settle(app)
    # the scoring claim: the end must not score the turn a second time. The second call is the end's second opinion
    assert model.calls["evaluator"] == 2
    debrief_request = [request for request in model.requests if request.role == "debrief"][-1]
    payload = json.loads(debrief_request.messages[1]["content"])
    assert payload["scores"] and payload["scores"][0]["turn"] == 1  # the debrief carries the waited-for score


async def test_a_scorer_sees_the_transcript_only_up_to_its_turn(app, new_client):
    model = use_model(app)
    model.answers["evaluator"].extend(["not json", "not json"])  # the scoring of turn 1 fails, left unscored
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "First message.")
    await settle(app)  # the two malformed evaluator calls of turn 1
    await say(alice, session["id"], "Second message.")
    await settle(app)  # turn 2 is scored
    await alice.post(f"/api/sessions/{session['id']}/end")
    await settle(app)  # the end re-scores turn 1
    transcripts = [
        json.loads(request.messages[1]["content"])["transcript"]
        for request in model.requests
        if request.role == "evaluator"
    ]
    assert len(transcripts) == 5  # the last one is the end's second opinion, over the whole conversation
    assert len(transcripts[3]) == 3  # the opening line and turn 1 only
    assert len(transcripts[4]) == 5
    assert all("Second message." not in line["text"] for line in transcripts[3])


async def test_the_debrief_lists_what_stayed_hidden_and_checks_its_quotes(app, new_client):
    model = use_model(app)
    model.answers["debrief"].append(
        json.dumps(
            {
                "summary": "s",
                "strengths": [],
                "improvements": [],
                "did_well": [{"turn": 1, "note": "Asked.", "quote": "What worries you"}],
                "missed": [{"turn": 1, "note": "Invented.", "quote": "never said", "try_instead": "Ask."}],
                "one_focus": {"title": "Identify interests", "advice": "Ask why."},
            }
        )
    )
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "What worries you most?")
    await alice.post(f"/api/sessions/{session['id']}/end")
    await settle(app)
    out = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert out["debrief"]["did_well"] == [{"turn": 1, "note": "Asked.", "quote": "What worries you"}]
    assert out["debrief"]["missed"] == [] and out["debrief"]["one_focus"]["title"] == "Identify interests"
    facts = {fact["id"]: fact for fact in out["hidden_facts"]}
    assert set(facts) == {"loss_of_control", "security_blame"} and not any(f["found"] for f in facts.values())
    assert facts["security_blame"]["unlock"] == "trust at 65 or more"
    assert facts["loss_of_control"]["unlock"] == 'the "identifies interest" move or trust at 55 or more'
    assert out["dimensions"]["questioning"] == "Quality of questioning"


async def test_a_fact_the_trainee_drew_out_is_marked_found(app, new_client):
    model = use_model(app)
    model.answers["classifier"].append(
        json.dumps({"moves": [{"id": "identifies_interest", "quote": "afraid of losing"}]})
    )
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "Are your commanders afraid of losing control of the camp?")
    await alice.post(f"/api/sessions/{session['id']}/end")
    await settle(app)
    out = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    facts = {fact["id"]: fact for fact in out["hidden_facts"]}
    assert facts["loss_of_control"]["found"] and facts["loss_of_control"]["unlock"] == ""
    assert not facts["security_blame"]["found"]


async def test_the_debrief_explains_why_the_dials_moved(app, new_client):
    model = use_model(app)
    model.answers["classifier"].append(
        json.dumps({"moves": [{"id": "identifies_interest", "quote": "afraid of losing"}]})
    )
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "Are your commanders afraid of losing control of the camp?")
    model.replies.append(["Delegate, my time is limited."])
    await nudge(alice, session["id"])
    await alice.post(f"/api/sessions/{session['id']}/end")
    await settle(app)
    causes = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()["dial_causes"]
    move = next(cause for cause in causes if cause["kind"] == "move")
    assert move["turn"] == 1 and move["label"] == "identifies interest" and move["quote"] == "afraid of losing"
    assert move["changes"] == {"rigidity": -15, "trust": 5}
    silence = next(cause for cause in causes if cause["kind"] == "silence")
    assert silence["turn"] == 2 and silence["quote"] == "" and silence["changes"] == {"hostility": 5}
    assert all(cause["changes"] for cause in causes)  # a cause that moved nothing is not listed


def _score(value: int) -> str:
    return json.dumps({"scores": [{"id": "questioning", "score": value, "quote": "What worries you"}]})


async def test_the_debrief_carries_a_second_scoring_pass_and_flags_a_wide_gap(app, new_client):
    model = use_model(app)
    model.answers["evaluator"].extend([_score(4), _score(1)])  # the turn's score, then the second opinion at the end
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "What worries you most?")
    await settle(app)
    await alice.post(f"/api/sessions/{session['id']}/end")
    await settle(app)
    out = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert out["scores"]["scores"][0]["score"] == 4  # the figure shown is the first pass's
    assert out["debrief"]["score_check"] == [{"id": "questioning", "first": 4, "second": 1, "uncertain": True}]
    assert model.calls["evaluator"] == 2
    assert [role for role, _ in await ledger(app, session["id"])].count("evaluator") == 2


async def test_two_passes_within_a_point_are_not_uncertain(app, new_client):
    model = use_model(app)
    model.answers["evaluator"].extend([_score(4), _score(3)])
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "What worries you most?")
    await settle(app)
    await alice.post(f"/api/sessions/{session['id']}/end")
    await settle(app)
    check = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()["debrief"]["score_check"]
    assert check == [{"id": "questioning", "first": 4, "second": 3, "uncertain": False}]


async def test_a_failed_second_pass_leaves_the_debrief_without_a_check(app, new_client):
    model = use_model(app)
    model.answers["evaluator"].extend([_score(4), "not json", "not json"])
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "What worries you most?")
    await settle(app)
    await alice.post(f"/api/sessions/{session['id']}/end")
    await settle(app)
    out = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert out["status"] == "ready" and out["debrief"]["score_check"] == []
