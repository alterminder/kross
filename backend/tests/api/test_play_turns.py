import asyncio
import copy
import gc
import json
import time
import uuid
from contextlib import suppress
from datetime import timedelta

import pytest
from sqlalchemy import select, update

import nlab.api.play as play_api
from nlab.db.auth_sessions import utcnow
from nlab.db.models import LlmCall, PlaySession, Status, Turn
from nlab.db.sessions import CLAIM_TIMEOUT
from nlab.llm.types import Usage
from tests.api.support import (
    PLAYER_SESSION_KEYS,
    card_id,
    count,
    done_of,
    ledger,
    nudge,
    reply_of,
    say,
    seed_curated,
    settle,
    sign_in,
    start_play,
    use_model,
)

pytestmark = pytest.mark.anyio


async def playing(app, new_client, cover="camp"):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    return alice, await start_play(alice, await card_id(alice, cover))


async def stored_state(app, session_id):
    async with app.state.sessionmaker() as db:
        return await db.scalar(select(PlaySession.engine_state).where(PlaySession.id == session_id))


async def claim_of(app, session_id):
    async with app.state.sessionmaker() as db:
        return await db.scalar(select(PlaySession.turn_in_progress).where(PlaySession.id == session_id))


def raw_scope(alice, path):
    cookie = "; ".join(f"{name}={value}" for name, value in alice.cookies.items())
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},  # what uvicorn 0.54 reports
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"test"),
            (b"content-type", b"application/json"),
            (b"x-requested-with", b"nlab"),
            (b"cookie", cookie.encode()),
        ],
        "client": ("127.0.0.1", 5000),
        "server": ("test", 80),
        "state": {},
    }


def disconnecting(body: bytes, at: int):
    """receive/send for a raw ASGI call whose client leaves after `at` reply chunks, between two chunks."""
    gone, first, seen = asyncio.Event(), [True], [0]

    async def receive():
        if first[0]:
            first[0] = False
            return {"type": "http.request", "body": body, "more_body": False}
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and b"event: reply" in message.get("body", b""):
            seen[0] += 1
            if seen[0] == at:
                gone.set()
            await asyncio.sleep(0)  # the send yields: the generator parks here between chunks

    return receive, send


async def test_a_turn_streams_the_reply_and_saves_it(app, new_client):
    model = use_model(app)
    model.replies.append(["We will ", "see.", Usage(7, 3)])
    alice, session = await playing(app, new_client)
    events = await say(alice, session["id"], "Good morning. What worries you most?")
    assert reply_of(events) == "We will see."
    assert done_of(events) == {"turn": 1, "ended": False, "outcome": None}
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert set(read) == PLAYER_SESSION_KEYS and read["turn"] == 1
    assert [line["role"] for line in read["transcript"]] == ["character", "trainee", "character"]
    await settle(app)
    async with app.state.sessionmaker() as db:
        roles = sorted(await db.scalars(select(LlmCall.role).where(LlmCall.session_id == session["id"])))
    assert roles == ["classifier", "counterpart", "evaluator"]


async def test_evidence_without_a_quote_changes_no_dial(app, new_client):
    model = use_model(app)
    model.answers["classifier"].append(
        json.dumps({"moves": [{"id": "shows_respect_curiosity", "quote": "never said"}]})
    )
    alice, session = await playing(app, new_client)
    before = (await stored_state(app, session["id"]))["dials"]
    await say(alice, session["id"], "Hello.")
    assert (await stored_state(app, session["id"]))["dials"] == before


async def test_a_quoted_move_moves_the_dials(app, new_client):
    model = use_model(app)
    model.answers["classifier"].append(
        json.dumps({"moves": [{"id": "shows_respect_curiosity", "quote": "I hear your concern"}]})
    )
    alice, session = await playing(app, new_client)
    before = (await stored_state(app, session["id"]))["dials"]["trust"]
    await say(alice, session["id"], "I hear your concern.")
    assert (await stored_state(app, session["id"]))["dials"]["trust"] > before


async def test_one_turn_at_a_time(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client)
    async with app.state.sessionmaker() as db:
        await db.execute(update(PlaySession).values(turn_in_progress=utcnow()))
        await db.commit()
    busy = await alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Hello?"})
    assert busy.status_code == 409
    async with app.state.sessionmaker() as db:  # an abandoned claim (older than 180 s) no longer blocks
        await db.execute(update(PlaySession).values(turn_in_progress=utcnow().replace(year=2000)))
        await db.commit()
    assert done_of(await say(alice, session["id"], "Hello?"))["turn"] == 1


async def test_reconcile_get_during_a_running_turn_reports_the_old_turn_then_the_turn_commits(app, new_client):
    """What Play's reconciliation GET sees while a dropped turn is still running: the old turn, but turn_running."""
    model = use_model(app)
    gate = model.once["classifier"] = asyncio.Event()
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    # the client's connection is gone (network change), but the server has not noticed: the turn keeps running
    running = asyncio.create_task(say(alice, session["id"], "Hello."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)
    seen = (await alice.get(f"/api/sessions/{session['id']}")).json()  # Play's reconciliation GET
    assert seen["turn_running"] is True  # the client can see the turn is still running and wait instead of resending
    assert seen["turn"] == 0
    assert not any(line["role"] == "trainee" for line in seen["transcript"])
    resend = await alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Hello."})
    assert resend.status_code == 409  # a quick resend is refused: Play restores the text again
    gate.set()
    assert done_of(await asyncio.wait_for(running, timeout=10))["turn"] == 1  # the "unsaved" turn commits after all
    later = await asyncio.wait_for(say(alice, session["id"], "Hello."), timeout=10)  # the trainee resends as told
    assert done_of(later)["turn"] == 2
    final = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert final["turn_running"] is False
    assert [line["text"] for line in final["transcript"] if line["role"] == "trainee"] == ["Hello.", "Hello."]


async def test_turn_running_is_false_on_an_ended_session_while_the_debrief_is_written(app, new_client):
    """claim_finish reuses the turn slot, but the finisher's claim is not a turn: an ended session never runs one."""
    model = use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "checkpoint"))
    line = next(item["text"] for item in session["brief"]["red_lines"] if "payment" in item["text"].lower())
    model.answers["classifier"].append(
        json.dumps({"red_lines": [{"text": line, "quote": "pay you", "action": "offers"}]})
    )
    gate = model.gates["debrief"] = asyncio.Event()
    events = await say(alice, session["id"], "I will pay you to let us through.")
    assert done_of(events)["ended"]
    await asyncio.wait_for(model.entered["debrief"].wait(), timeout=10)
    seen = (await alice.get(f"/api/sessions/{session['id']}")).json()
    try:
        assert seen["status"] == "ended" and seen["turn"] == 1
        assert seen["turn_running"] is False  # no turn runs: the claim on the slot belongs to the debrief finisher
    finally:
        gate.set()
        for _ in range(100):  # let the finisher write before teardown
            if (await alice.get(f"/api/sessions/{session['id']}")).json()["debrief_status"] != "pending":
                break
            await asyncio.sleep(0.05)
    after = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert after["turn_running"] is False


async def test_turn_running_is_false_after_end_while_the_debrief_is_written(app, new_client):
    model = use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    assert done_of(await say(alice, session["id"], "Hello."))["turn"] == 1
    gate = model.gates["debrief"] = asyncio.Event()
    ended = await alice.post(f"/api/sessions/{session['id']}/end")
    assert ended.status_code == 200 and ended.json()["turn_running"] is False
    await asyncio.wait_for(model.entered["debrief"].wait(), timeout=10)
    seen = (await alice.get(f"/api/sessions/{session['id']}")).json()
    try:
        assert seen["status"] == "ended" and seen["turn_running"] is False
    finally:
        gate.set()
        for _ in range(100):
            if (await alice.get(f"/api/sessions/{session['id']}")).json()["debrief_status"] != "pending":
                break
            await asyncio.sleep(0.05)


async def test_turn_running_stays_true_past_the_claim_timeout_while_the_turn_can_still_commit(
    app, new_client, monkeypatch
):
    """A claim, however old, can still commit until another replaces it: running never ages out mid-turn."""
    model = use_model(app)
    gate = model.once["classifier"] = asyncio.Event()
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    running = asyncio.create_task(say(alice, session["id"], "Hello."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)
    real = play_api.utcnow
    monkeypatch.setattr(play_api, "utcnow", lambda: real() + CLAIM_TIMEOUT + timedelta(seconds=1))  # 181 s later
    seen = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert seen["turn_running"] is True and seen["turn"] == 0  # the honest answer while the write can still land
    gate.set()
    events = await asyncio.wait_for(running, timeout=10)
    assert done_of(events)["turn"] == 1  # the gated turn commits anyway: nobody took the claim over


async def test_a_red_line_ends_the_session_without_a_reply(app, new_client):
    model = use_model(app)
    alice, session = await playing(app, new_client, "checkpoint")
    brief = session["brief"]
    line = next(item["text"] for item in brief["red_lines"] if "payment" in item["text"].lower())
    model.answers["classifier"].append(
        json.dumps({"red_lines": [{"text": line, "quote": "pay you", "action": "offers"}]})
    )
    events = await say(alice, session["id"], "I will pay you to let us through.")
    assert reply_of(events) == "" and model.calls["counterpart"] == 0
    done = done_of(events)
    assert done["ended"] and done["outcome"]["result"] == "fail"
    assert (await alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Sorry."})).status_code == 410


async def test_a_failed_classification_changes_nothing(app, new_client):
    model = use_model(app)
    model.answers["classifier"].extend(["not json", "still not json"])
    alice, session = await playing(app, new_client)
    events = await say(alice, session["id"], "Hello.")
    assert [event for event, _ in events] == ["error"]
    assert events == [("error", {"detail": "The model's answer was unusable. Send your message again."})]
    assert await ledger(app, session["id"]) == [("classifier", "malformed")]
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["turn"] == 0 and len(read["transcript"]) == 1
    assert done_of(await say(alice, session["id"], "Hello again."))["turn"] == 1  # the claim was released


async def test_a_silent_counterpart_leaves_a_placeholder_and_the_turn_counts(app, new_client):
    model = use_model(app)
    model.replies.extend([["HANG"], ["HANG"]])
    alice, session = await playing(app, new_client)
    events = await asyncio.wait_for(say(alice, session["id"], "Hello."), timeout=10)
    assert any(event == "notice" for event, _ in events)
    assert ("notice", {"detail": "(The counterpart does not answer. You can continue.)"}) in events
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["turn"] == 1 and read["transcript"][-1]["text"].startswith("(The counterpart does not answer")


async def own_scenario_with_fallback(app, new_client, line="I cannot discuss this now. Come back to it later."):
    from tests.api.support import draft

    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    content = draft()
    content["counterparts"][0]["fallback"] = line
    made = await alice.post("/api/scenarios", json={"content": content})
    assert made.status_code == 201, made.text
    return alice, await start_play(alice, made.json()["id"])


async def test_a_silent_counterpart_speaks_its_fallback_line_in_character(app, new_client):
    model = use_model(app)
    model.replies.extend([["HANG"], ["HANG"]])
    alice, session = await own_scenario_with_fallback(app, new_client)
    events = await asyncio.wait_for(say(alice, session["id"], "Hello."), timeout=10)
    assert ("reply", {"text": "I cannot discuss this now. Come back to it later."}) in events
    assert not any(event == "notice" for event, _ in events)  # no system note: the counterpart simply speaks
    assert done_of(events)["turn"] == 1
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["transcript"][-1] == {
        "role": "character",
        "text": "I cannot discuss this now. Come back to it later.",
        "turn": 1,
        "speaker": "militia_rep",  # every line names its speaker now, single-party included
    }
    assert model.calls["grant"] == 0  # the line is the author's, not a reply to be checked for a grant


async def test_a_silent_counterpart_speaks_its_fallback_line_after_a_nudge(app, new_client):
    model = use_model(app)
    model.replies.extend([["HANG"], ["HANG"]])
    alice, session = await own_scenario_with_fallback(app, new_client, "Time is short, delegate.")
    events = await asyncio.wait_for(nudge(alice, session["id"]), timeout=10)
    assert ("reply", {"text": "Time is short, delegate."}) in events and done_of(events)["turn"] == 1


async def test_a_granted_offer_ends_the_session_with_success(app, new_client):
    model = use_model(app)
    alice, session = await playing(app, new_client, "checkpoint")
    async with app.state.sessionmaker() as db:  # put the dials in the success range, as a long good conversation would
        row = await db.get_one(PlaySession, session["id"])
        state = dict(row.engine_state)
        state["dials"] = {**state["dials"], "trust": 70, "rigidity": 45, "hostility": 30}
        row.engine_state = state
        await db.commit()
    assert not done_of(await say(alice, session["id"], "We carry food and medicine."))["ended"]  # offered now
    model.answers["classifier"].append(json.dumps({"asked_for_goal": True}))
    model.replies.append(["Very well. You may pass."])
    model.answers["grant"].append(json.dumps({"granted": True, "quote": "You may pass"}))
    done = done_of(await say(alice, session["id"], "Yes, please let us pass."))
    assert done["ended"] and done["outcome"]["result"] == "success"
    assert ("grant", "ok") in await ledger(app, session["id"])


async def test_the_frozen_counterpart_request_is_stored_per_turn(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client)
    await say(alice, session["id"], "Hello.")
    async with app.state.sessionmaker() as db:
        request = await db.scalar(select(Turn.counterpart_request).where(Turn.number == 1))
    assert request["role"] == "counterpart" and request["messages"][0]["role"] == "system"


async def test_without_a_model_turns_are_unavailable(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    assert (await alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Hi"})).status_code == 503
    assert await count(app, Turn) == 1


async def test_a_client_disconnect_mid_reply_releases_the_claim(app, new_client):
    """A tab closed after the first reply chunk cancels the stream; the turn must not stay claimed (E1)."""
    model = use_model(app)
    model.replies.append(["Hello ", "HANG"])  # first words arrive, then the stream hangs
    alice, session = await playing(app, new_client)
    body = json.dumps({"text": "Good morning."}).encode()
    path = f"/api/sessions/{session['id']}/turns"
    scope = raw_scope(alice, path)
    gone, first = asyncio.Event(), [True]

    async def receive():
        if first[0]:
            first[0] = False
            return {"type": "http.request", "body": body, "more_body": False}
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and b"event: reply" in message.get("body", b""):
            gone.set()  # the browser tab closes after the first words

    # the cancelled stream may surface here; the cleanup inside the app must not
    with suppress(Exception, asyncio.CancelledError):
        await asyncio.wait_for(app(scope, receive, send), timeout=10)
    await asyncio.sleep(0.5)
    async with app.state.sessionmaker() as db:
        stored = await db.get_one(PlaySession, session["id"])
    assert stored.turn_in_progress is None  # the claim was released despite the disconnect
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["turn"] == 0  # the interrupted turn was not saved
    assert done_of(await asyncio.wait_for(say(alice, session["id"], "Hello again."), timeout=10))["turn"] == 1


async def test_a_counterpart_provider_error_saves_nothing(app, new_client):
    """A provider error mid-stream (E6): an error event, no turn saved, the claim freed for a resend."""
    model = use_model(app)
    model.replies.append(["Hello ", RuntimeError("provider 500")])
    alice, session = await playing(app, new_client)
    events = await say(alice, session["id"], "Hello.")
    assert events == [
        ("reply", {"text": "Hello "}),
        ("error", {"detail": "The language model did not answer. Send your message again."}),
    ]
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["turn"] == 0 and len(read["transcript"]) == 1
    assert await ledger(app, session["id"]) == [("classifier", "ok"), ("counterpart", "error")]
    assert done_of(await say(alice, session["id"], "Hello again."))["turn"] == 1  # the claim was released


async def test_a_grant_check_error_still_saves_the_turn(app, new_client):
    """A provider error in the grant check (E5): the reply was already shown, so the turn counts, not granted."""
    model = use_model(app)
    alice, session = await playing(app, new_client, "checkpoint")
    async with app.state.sessionmaker() as db:  # dials in the range where the offer goes on the table
        row = await db.get_one(PlaySession, session["id"])
        state = dict(row.engine_state)
        state["dials"] = {**state["dials"], "trust": 70, "rigidity": 45, "hostility": 30}
        row.engine_state = state
        await db.commit()
    assert not done_of(await say(alice, session["id"], "We carry food and medicine."))["ended"]  # offered now
    model.answers["classifier"].append(json.dumps({"asked_for_goal": True}))
    model.replies.append(["Very well. You may pass."])
    model.answers["grant"].append(RuntimeError("provider 502"))
    events = await say(alice, session["id"], "Yes, please let us pass.")
    assert done_of(events) == {"turn": 2, "ended": False, "outcome": None}
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["turn"] == 2 and read["transcript"][-1]["text"] == "Very well. You may pass."
    assert ("grant", "error") in await ledger(app, session["id"])


async def test_a_classifier_provider_error_stays_on_the_ledger(app, new_client):
    model = use_model(app)
    model.answers["classifier"].append(RuntimeError("provider 500"))
    alice, session = await playing(app, new_client)
    events = await say(alice, session["id"], "Hello.")
    assert [event for event, _ in events] == ["error"]
    assert model.calls["classifier"] == 1  # one paid call happened
    assert await ledger(app, session["id"]) == [("classifier", "error")]


async def test_the_grant_check_is_not_run_after_the_silence_placeholder(app, new_client):
    model = use_model(app)
    alice, session = await playing(app, new_client, "checkpoint")
    async with app.state.sessionmaker() as db:  # dials in the range where the offer goes on the table
        row = await db.get_one(PlaySession, session["id"])
        state = dict(row.engine_state)
        state["dials"] = {**state["dials"], "trust": 70, "rigidity": 45, "hostility": 30}
        row.engine_state = state
        await db.commit()
    assert not done_of(await say(alice, session["id"], "We carry food and medicine."))["ended"]  # offered now
    model.replies.extend([["HANG"], ["HANG"]])  # the counterpart goes silent on the accepting turn
    events = await asyncio.wait_for(say(alice, session["id"], "Yes, please let us pass."), timeout=10)
    assert ("notice", {"detail": "(The counterpart does not answer. You can continue.)"}) in events
    assert model.calls["grant"] == 0  # a placeholder is not a granting reply
    assert done_of(events) == {"turn": 2, "ended": False, "outcome": None}


async def test_a_disconnect_between_chunks_releases_the_claim_at_once(app, new_client):
    """E1e: the client leaves while the stream is parked at a yield between chunks. The claim must be released now:
    the GC is off, so only a real cleanup (not a garbage collection) passes."""
    model = use_model(app)
    alice, session = await playing(app, new_client)
    path = f"/api/sessions/{session['id']}/turns"
    body = json.dumps({"text": "Good morning."}).encode()
    for attempt in range(5):
        model.replies.append([f"w{i} " for i in range(400)])
        receive, send = disconnecting(body, 3 + attempt * 5)
        gc.disable()
        try:
            with suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(app(raw_scope(alice, path), receive, send), timeout=10)
            await asyncio.sleep(0.3)
            held = (await claim_of(app, session["id"])) is not None
        finally:
            gc.enable()
        assert not held  # released at once, without any garbage collection


async def test_a_disconnect_between_chunks_needs_no_garbage_collection(app, new_client):
    """E1g: the same with the GC on and nobody collecting: the claim is released immediately, not seconds later."""
    model = use_model(app)
    alice, session = await playing(app, new_client)
    path = f"/api/sessions/{session['id']}/turns"
    body = json.dumps({"text": "Good morning."}).encode()
    model.replies.append([f"w{i} " for i in range(400)])
    receive, send = disconnecting(body, 7)
    with suppress(Exception, asyncio.CancelledError):
        await asyncio.wait_for(app(raw_scope(alice, path), receive, send), timeout=10)
    started = time.monotonic()
    while (await claim_of(app, session["id"])) is not None and time.monotonic() - started < 8:
        await asyncio.sleep(0.05)
    assert time.monotonic() - started < 1  # the release did not wait for a garbage collection


async def test_a_stale_turn_loses_the_takeover_cleanly(app, new_client):
    """A turn outlives its claim, a second message takes the claim over and completes; the stale turn's write is
    refused with an error event and only the takeover's turn is saved."""
    model = use_model(app)
    gate = model.once["classifier"] = asyncio.Event()
    alice, session = await playing(app, new_client)
    first = asyncio.create_task(say(alice, session["id"], "A message."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)
    async with app.state.sessionmaker() as db:  # the claim is now stale and taken over below
        await db.execute(update(PlaySession).values(turn_in_progress=utcnow().replace(year=2000)))
        await db.commit()
    second = await asyncio.wait_for(say(alice, session["id"], "B message."), timeout=10)
    assert done_of(second)["turn"] == 1
    gate.set()
    events = await asyncio.wait_for(first, timeout=10)
    assert events[-1] == ("error", {"detail": "The session changed while the model was working; nothing was saved."})
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["turn"] == 1


async def test_a_release_never_clears_another_turns_claim(app, new_client):
    """A failing turn releases only its own claim token: a later turn's live claim survives it."""
    model = use_model(app)
    gate = model.once["classifier"] = asyncio.Event()
    alice, session = await playing(app, new_client)
    # the first call to arrive (turn A) parks at `gate` and then fails; the second (turn B) answers normally
    model.answers["classifier"].extend(['{"moves": [], "asked_for_goal": false}', RuntimeError("boom")])
    model.gates["counterpart"] = asyncio.Event()  # B parks mid-turn with its claim live
    first = asyncio.create_task(say(alice, session["id"], "A message."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)
    async with app.state.sessionmaker() as db:  # A's claim is now stale and B takes it over
        await db.execute(update(PlaySession).values(turn_in_progress=utcnow().replace(year=2000)))
        await db.commit()
    second = asyncio.create_task(say(alice, session["id"], "B message."))
    await asyncio.wait_for(model.entered["counterpart"].wait(), timeout=10)
    gate.set()
    failed = await asyncio.wait_for(first, timeout=10)
    assert [event for event, _ in failed] == ["error"]
    busy = await asyncio.wait_for(
        alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "C message."}), timeout=10
    )
    assert busy.status_code == 409  # B's claim is still B's: A's failed release must not clear it
    model.gates["counterpart"].set()
    assert done_of(await asyncio.wait_for(second, timeout=10))["turn"] == 1


async def test_a_final_write_never_lands_on_an_ended_session(app, new_client):
    """The status condition of the claim-conditional write is a guard of its own: even when the claim token still
    matches, a running turn must never write into an ended session."""
    model = use_model(app)
    gate = model.once["classifier"] = asyncio.Event()
    alice, session = await playing(app, new_client)
    turn = asyncio.create_task(say(alice, session["id"], "A message."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)
    outcome = {"id": "ended_by_trainee", "label": "Session ended by the trainee", "result": "ended", "turn": 0}
    async with app.state.sessionmaker() as db:  # an end that left the running turn's claim in place
        row = await db.get_one(PlaySession, session["id"])
        state = dict(row.engine_state)
        state["outcome"] = outcome
        row.engine_state = state
        row.status = Status.ended
        row.ended_at = utcnow()
        row.debrief_status = "pending"
        await db.commit()
    gate.set()
    events = await asyncio.wait_for(turn, timeout=10)
    assert events[-1] == ("error", {"detail": "The session changed while the model was working; nothing was saved."})
    assert (await stored_state(app, session["id"]))["outcome"] == outcome


async def test_a_grant_call_stays_on_the_ledger_when_the_write_loses(app, new_client):
    """E14: a grant check over a stale claim whose turn then loses to /end: the paid call stays on the ledger even
    though the turn itself is rolled back."""
    model = use_model(app)
    alice, session = await playing(app, new_client, "checkpoint")
    async with app.state.sessionmaker() as db:  # dials in the range where the offer goes on the table
        row = await db.get_one(PlaySession, session["id"])
        state = dict(row.engine_state)
        state["dials"] = {**state["dials"], "trust": 70, "rigidity": 45, "hostility": 30}
        row.engine_state = state
        await db.commit()
    assert not done_of(await say(alice, session["id"], "We carry food and medicine."))["ended"]  # offered now
    model.replies.append(["Very well. You may pass."])
    model.answers["grant"].append('{"granted": false, "quote": ""}')
    gate = model.once["grant"] = asyncio.Event()
    turn = asyncio.create_task(say(alice, session["id"], "Yes, please let us pass."))
    await asyncio.wait_for(model.entered["grant"].wait(), timeout=10)
    async with app.state.sessionmaker() as db:  # the claim is now stale and /end takes the session
        await db.execute(update(PlaySession).values(turn_in_progress=utcnow().replace(year=2000)))
        await db.commit()
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    gate.set()
    events = await asyncio.wait_for(turn, timeout=10)
    assert events[-1][0] == "error"  # the turn's write lost to /end
    await settle(app)
    assert ("grant", "ok") in await ledger(app, session["id"])


async def test_inactivity_silence_nudge(app, new_client):
    """Calling /nudge triggers an in-character prompt and applies a silence penalty to dials."""
    model = use_model(app)
    alice, session = await playing(app, new_client, "checkpoint")
    model.replies.append(["Delegate, my time is limited. What do you want?"])

    events = await nudge(alice, session["id"])
    assert reply_of(events) == "Delegate, my time is limited. What do you want?"
    assert done_of(events)["turn"] == 1

    async with app.state.sessionmaker() as db:
        turn = await db.scalar(select(Turn).where(Turn.session_id == session["id"], Turn.number == 1))
        assert turn is not None
        assert turn.trainee_text == "(The delegate remains silent.)"
        assert turn.reply_text == "Delegate, my time is limited. What do you want?"
        assert any(e.get("reason") == "Trainee silence / hesitation" for e in turn.events)

    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["turn"] == 1
    assert read["phase"] == "opening"


async def test_nudges_trigger_failure_rules_and_end_session(app, new_client):
    """Multiple silence nudges increase hostility until the scenario's failure rule triggers."""
    model = use_model(app)
    alice, session = await playing(app, new_client, "checkpoint")
    sid = session["id"]

    # In checkpoint scenario, initial hostility is 60.
    # Nudges add +5 hostility each. At 6 nudges, hostility reaches 90.
    # Failure rule: hostility_gte: 90 -> checkpoint_denied ("Checkpoint turned around").
    for i in range(5):
        model.replies.append([f"Waiting turn {i + 1}."])
        events = await nudge(alice, sid)
        done = done_of(events)
        assert done["turn"] == i + 1
        assert done["ended"] is False
        assert done["outcome"] is None

    # 6th nudge hits hostility 90 and triggers failure
    model.replies.append(["Turn around immediately!"])
    events = await nudge(alice, sid)
    done = done_of(events)
    assert done["turn"] == 6
    assert done["ended"] is True
    assert done["outcome"] is not None
    assert done["outcome"]["result"] == "fail"
    assert done["outcome"]["label"] == "Convoy turned around"

    read = (await alice.get(f"/api/sessions/{sid}")).json()
    assert read["status"] == "ended"
    assert read["outcome"]["result"] == "fail"


async def test_nudge_resets_goal_requested(app, new_client):
    """A silence nudge must reset goal_requested to False, preventing agree_now cues."""
    model = use_model(app)
    alice, session = await playing(app, new_client, "checkpoint")
    sid = session["id"]

    # Turn 1: Trainee asks for goal
    model.answers["classifier"].append('{"moves": [], "asked_for_goal": true}')
    model.replies.append(["Let me see your paperwork."])
    await say(alice, sid, "Can we pass the checkpoint?")

    async with app.state.sessionmaker() as db:
        ps = await db.get_one(PlaySession, uuid.UUID(sid))
        assert ps.engine_state["goal_requested"] is True

    # Turn 2: Trainee is silent (nudge)
    model.replies.append(["Are you going to answer?"])
    events = await nudge(alice, sid)
    assert done_of(events)["turn"] == 2

    async with app.state.sessionmaker() as db:
        ps = await db.get_one(PlaySession, uuid.UUID(sid))
        assert ps.engine_state["goal_requested"] is False
        turn2 = await db.scalar(select(Turn).where(Turn.session_id == uuid.UUID(sid), Turn.number == 2))
        cue_kinds = [e.get("cue", {}).get("kind") for e in turn2.events if e.get("kind") == "cue"]
        assert "agree_now" not in cue_kinds


async def test_a_scenarios_own_stages_reach_the_player_without_their_instructions_and_steer_the_counterpart(
    app, new_client
):
    from tests.api.support import draft

    model = use_model(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    content = draft()
    content["timing"] = {
        "phases": [
            {
                "id": "cold_start",
                "label": "Cold start",
                "hint": "He says little.",
                "instruction": "SECRET: say little.",
                "until_turn": 1,
            },
            {"id": "the_ask", "instruction": "SECRET: press for terms."},
        ],
        "warnings": [2, 6],
        "on_timeout": "end",
    }
    made = await alice.post("/api/scenarios", json={"content": content})
    assert made.status_code == 201, made.text
    session = await start_play(alice, made.json()["id"])
    assert session["phase"] == "cold_start"
    assert session["phases"] == [
        {"id": "cold_start", "label": "Cold start", "hint": "He says little."},
        {"id": "the_ask", "label": "The ask", "hint": ""},
    ]
    assert session["warning_minutes"] == [6, 2] and session["on_timeout"] == "end"
    assert "SECRET" not in json.dumps(session)  # the counterpart's instruction never reaches the trainee
    await say(alice, session["id"], "Good morning.")
    await say(alice, session["id"], "May we talk about the convoy?")
    prompts = [request.messages[0]["content"] for request in model.requests if request.role == "counterpart"]
    assert "SECRET: say little." in prompts[0] and "SECRET: press for terms." in prompts[1]
    assert (await alice.get(f"/api/sessions/{session['id']}")).json()["phase"] == "the_ask"


async def timed_scenario(app, new_client, on_timeout=None):
    from tests.api.support import draft

    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    content = draft()
    if on_timeout:
        content["timing"] = {"on_timeout": on_timeout}
    made = await alice.post("/api/scenarios", json={"content": content})
    assert made.status_code == 201, made.text
    return alice, await start_play(alice, made.json()["id"])


async def run_out_the_clock(app, session_id):
    from datetime import timedelta

    from sqlalchemy import update

    from nlab.db.auth_sessions import utcnow

    async with app.state.sessionmaker() as db:
        await db.execute(
            update(PlaySession).where(PlaySession.id == session_id).values(created_at=utcnow() - timedelta(hours=3))
        )
        await db.commit()


async def test_when_time_runs_out_a_scenario_that_ends_the_meeting_refuses_the_next_turn_and_ends(app, new_client):
    use_model(app)
    alice, session = await timed_scenario(app, new_client, "end")
    assert done_of(await say(alice, session["id"], "Good morning."))["turn"] == 1  # there is time left
    await run_out_the_clock(app, session["id"])
    refused = await alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "One more thing."})
    assert refused.status_code == 410 and "Time is up" in refused.json()["detail"]
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["status"] == "ended" and read["outcome"] == {"result": "ended", "label": "Time ran out"}
    assert read["turn"] == 1 and len(read["transcript"]) == 3  # the refused message was never saved
    await settle(app)
    assert (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()["status"] == "ready"


async def test_a_failing_scenario_ends_as_a_failure_also_on_a_nudge(app, new_client):
    use_model(app)
    alice, session = await timed_scenario(app, new_client, "fail")
    await run_out_the_clock(app, session["id"])
    refused = await alice.post(f"/api/sessions/{session['id']}/nudge")
    assert refused.status_code == 410
    outcome = (await alice.get(f"/api/sessions/{session['id']}")).json()["outcome"]
    assert outcome == {"result": "fail", "label": "Time ran out without an agreement"}


async def test_a_scenario_that_only_guides_keeps_taking_turns_after_time_is_up(app, new_client):
    use_model(app)
    alice, session = await timed_scenario(app, new_client)  # no timing: the default is "guide"
    await run_out_the_clock(app, session["id"])
    assert done_of(await say(alice, session["id"], "Still here."))["turn"] == 1
    assert (await alice.get(f"/api/sessions/{session['id']}")).json()["status"] == "active"
    assert (await alice.post(f"/api/sessions/{session['id']}/time-up")).status_code == 409


async def test_the_browsers_time_up_call_needs_the_servers_clock_to_agree(app, new_client):
    use_model(app)
    alice, session = await timed_scenario(app, new_client, "end")
    early = await alice.post(f"/api/sessions/{session['id']}/time-up")
    assert early.status_code == 409  # twenty minutes are left
    await run_out_the_clock(app, session["id"])
    ended = await alice.post(f"/api/sessions/{session['id']}/time-up")
    assert ended.status_code == 200 and ended.json()["outcome"]["label"] == "Time ran out"
    assert (await alice.post(f"/api/sessions/{session['id']}/time-up")).status_code == 410  # already ended


async def test_switch_interlocutor_endpoint(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client, "tripartite")
    session_id = session["id"]

    read = (await alice.get(f"/api/sessions/{session_id}")).json()
    assert "active_interlocutor" in read

    resp = await alice.post(f"/api/sessions/{session_id}/interlocutor", json={"interlocutor": "opposition_cmdr"})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["active_interlocutor"] == "opposition_cmdr"


async def test_turn_rejects_an_unknown_interlocutor(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client, "tripartite")
    session_id = session["id"]

    bad = await alice.post(f"/api/sessions/{session_id}/turns", json={"text": "Hello there", "interlocutor": "nobody"})
    assert bad.status_code == 400

    # a valid interlocutor on the turn itself still works
    events = await say_interlocutor(app, alice, session_id, "Hello there", "opposition_cmdr")
    assert any(event == "done" for event, _ in events)


async def say_interlocutor(app, alice, session_id, text, interlocutor):
    events: list = []
    current = ""
    async with alice.stream(
        "POST", f"/api/sessions/{session_id}/turns", json={"text": text, "interlocutor": interlocutor}
    ) as response:
        assert response.status_code == 200, await response.aread()
        async for raw in response.aiter_lines():
            if raw.startswith("event: "):
                current = raw.removeprefix("event: ")
            elif raw.startswith("data: "):
                events.append((current, json.loads(raw.removeprefix("data: "))))
    return events


async def test_a_silent_non_primary_speaker_gets_the_neutral_placeholder(app, new_client):
    from tests.api.support import CURATED

    model = use_model(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    content = copy.deepcopy(CURATED["s08_tripartite_siege"])
    content["id"], content["title"] = "s08_fallback_test", "Siege fallback test"
    content["counterparts"][0]["fallback"] = "The colonel waves you away."
    made = await alice.post("/api/scenarios", json={"content": content})
    assert made.status_code == 201, made.text
    session = await start_play(alice, made.json()["id"])

    # primary counterpart is silent: its own fallback line speaks
    model.replies.extend([["HANG"], ["HANG"]])
    events = await asyncio.wait_for(say(alice, session["id"], "Colonel?"), timeout=10)
    assert ("reply", {"text": "The colonel waves you away."}) in events

    # the other commander is silent: the neutral placeholder, never the colonel's line
    switched = await alice.post(f"/api/sessions/{session['id']}/interlocutor", json={"interlocutor": "opposition_cmdr"})
    assert switched.status_code == 200
    model.replies.extend([["HANG"], ["HANG"]])
    events = await asyncio.wait_for(say(alice, session["id"], "Commander?"), timeout=10)
    assert not any(data.get("text") == "The colonel waves you away." for event, data in events if event == "reply")
    assert any(event == "notice" for event, _ in events)


async def test_a_nudge_addresses_the_active_party_and_hides_other_channels(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client, "tripartite")
    session_id = session["id"]

    # a private line to the colonel
    await say(alice, session_id, "Colonel, our secret bottom line is two trucks.")
    # switch to the opposition commander, then fall silent
    switched = await alice.post(f"/api/sessions/{session_id}/interlocutor", json={"interlocutor": "opposition_cmdr"})
    assert switched.status_code == 200
    events = await asyncio.wait_for(nudge(alice, session_id), timeout=10)
    assert any(event == "done" for event, _ in events)

    async with app.state.sessionmaker() as db:
        request = await db.scalar(
            select(Turn.counterpart_request).where(Turn.session_id == uuid.UUID(session_id), Turn.number == 2)
        )
    system = request["messages"][0]["content"]
    assert "Opposition" in system  # Tareq's persona, not the colonel's
    said = [m["content"] for m in request["messages"][1:]]
    assert "Colonel, our secret bottom line is two trucks." not in said

    # the nudge reply is tagged with the party that spoke it
    read = (await alice.get(f"/api/sessions/{session_id}")).json()
    assert read["transcript"][-1]["speaker"] == "opposition_cmdr"


async def test_a_silent_nudge_for_a_non_primary_speaker_gets_the_placeholder(app, new_client):
    from tests.api.support import CURATED

    model = use_model(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    content = copy.deepcopy(CURATED["s08_tripartite_siege"])
    content["id"], content["title"] = "s08_nudge_fallback_test", "Siege nudge fallback test"
    content["counterparts"][0]["fallback"] = "The colonel waves you away."
    made = await alice.post("/api/scenarios", json={"content": content})
    assert made.status_code == 201, made.text
    session = await start_play(alice, made.json()["id"])

    switched = await alice.post(f"/api/sessions/{session['id']}/interlocutor", json={"interlocutor": "opposition_cmdr"})
    assert switched.status_code == 200
    model.replies.extend([["HANG"], ["HANG"]])
    events = await asyncio.wait_for(nudge(alice, session["id"]), timeout=10)
    assert not any(data.get("text") == "The colonel waves you away." for event, data in events if event == "reply")
    assert any(event == "notice" for event, _ in events)
