"""Live steering: dials, preset and free-text twists, and trainer comments."""

import asyncio
import json

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from nlab.db.models import LlmCall
from nlab.llm import LLMConfig, RoleConfig
from tests.api.support import (
    card_id,
    done_of,
    draft,
    join,
    ledger,
    org_with_admin,
    say,
    seed_curated,
    settle,
    sign_in,
    start_play,
    use_model,
)
from tests.api.test_limits import limit, spend

pytestmark = pytest.mark.anyio


def set_dial(client, session_id, value=80, dial="trust"):
    return client.post(f"/api/sessions/{session_id}/dials", json={"dial": dial, "value": value})


async def gated_twist(model, admin, session_id):
    """Starts a free-text twist paused inside its director call; the returned event releases it."""
    gate = model.once["director"] = asyncio.Event()
    pending = asyncio.create_task(admin.post(f"/api/sessions/{session_id}/twists", json={"text": "The river rises"}))
    await asyncio.wait_for(model.entered["director"].wait(), timeout=10)
    return gate, pending


async def member_session(app, new_client):
    """A curated solo session by bob, a member of the admin's org."""
    await seed_curated(app)
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    session = await start_play(bob, await card_id(bob, "camp"))
    return admin, bob, session


async def test_an_admin_sets_a_dial_on_a_members_session(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    await say(bob, session["id"], "Hello.")
    response = await set_dial(admin, session["id"], 80)
    assert response.status_code == 200, response.text
    assert response.json()["state"]["dials"]["trust"] == 80
    events = response.json()["turns"][-1]["events"]
    assert any(event["source"] == "trainer" and event["kind"] == "dial" and event["after"] == 80 for event in events)
    # the player's own session view still shows no dials
    mine = (await bob.get(f"/api/sessions/{session['id']}")).json()
    assert "state" not in mine and "dials" not in mine


async def test_the_player_of_a_solo_session_never_steers(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    assert (await set_dial(bob, session["id"], 80)).status_code == 403
    # whatever their role: a personal org's owner is its admin and still cannot steer their own solo session
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    own = await start_play(alice, await card_id(alice, "camp"))
    assert (await set_dial(alice, own["id"], 80)).status_code == 403


async def test_other_members_and_other_orgs_see_nothing(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    carol = new_client()
    await sign_in(carol, "carol", "carol@example.org")
    await join(carol, admin)
    assert (await set_dial(carol, session["id"], 80)).status_code in (403, 404)
    other, _ = await org_with_admin(new_client, "Other Delegation")
    assert (await set_dial(other, session["id"], 80)).status_code == 404


async def test_an_ended_session_and_a_bad_value_are_refused(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    assert (await set_dial(admin, session["id"], 101)).status_code == 422
    assert (await set_dial(admin, session["id"], -1)).status_code == 422
    assert (await set_dial(admin, session["id"], 50, "luck")).status_code == 422
    assert (await bob.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    assert (await set_dial(admin, session["id"], 80)).status_code == 410


async def test_a_running_turn_refuses_steering(app, new_client):
    model = use_model(app)
    gate = model.gates["classifier"] = asyncio.Event()
    admin, bob, session = await member_session(app, new_client)
    turn = asyncio.create_task(say(bob, session["id"], "A message."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)  # the turn holds its claim
    assert (await set_dial(admin, session["id"], 80)).status_code == 409
    assert (
        await admin.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    ).status_code == 409
    assert (await admin.post(f"/api/sessions/{session['id']}/twists", json={"text": "A twist"})).status_code == 409
    gate.set()
    assert done_of(await asyncio.wait_for(turn, timeout=10))["turn"] == 1


async def test_an_admin_fires_a_preset_twist_into_a_members_session(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    twisted = await admin.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    assert twisted.status_code == 200, twisted.text
    assert "military_call" in {item["id"] for item in twisted.json()["state"]["injections"]}
    assert twisted.json()["state"]["outcome"] is None  # a twist never ends the session by itself
    # the player of the solo session may not
    assert (
        await bob.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    ).status_code == 403


async def test_the_playtester_still_fires_twists_in_their_own_playtest(app, new_client):
    use_model(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    session = await start_play(alice, mine["id"], "playtest")
    twisted = await alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    assert twisted.status_code == 200
    assert "military_call" in {item["id"] for item in twisted.json()["state"]["injections"]}


async def test_a_free_text_twist_is_rewritten_checked_and_recorded(app, new_client):
    model = use_model(app)
    model.answers["director"].append('{"instruction": "News arrives: the river is rising."}')
    model.answers["bias"].append('{"flagged": true, "reason": "plays on a stereotype"}')
    admin, bob, session = await member_session(app, new_client)
    response = await admin.post(f"/api/sessions/{session['id']}/twists", json={"text": "The river is rising"})
    assert response.status_code == 200, response.text
    (record,) = [item for item in response.json()["state"]["injections"] if item["id"].startswith("free_")]
    assert record["original"] == "The river is rising"
    assert record["rewritten"] == "News arrives: the river is rising."
    assert record["instruction"] == "News arrives: the river is rising."
    assert record["bias"] == {"flagged": True, "reason": "plays on a stereotype"}
    assert ("bias", "ok") in await ledger(app, session["id"])
    assert ("director", "ok") in await ledger(app, session["id"])
    # the two calls count for the steering admin, in the admin's org, with the session id
    me = (await admin.get("/api/me")).json()
    async with app.state.sessionmaker() as db:
        rows = list(
            (
                await db.execute(
                    select(LlmCall).where(LlmCall.role.in_(("director", "bias")), LlmCall.session_id == session["id"])
                )
            ).scalars()
        )
        assert {str(row.user_id) for row in rows} == {me["id"]}
        assert {str(row.org_id) for row in rows} == {me["active_org"]["id"]}


async def test_a_rewritten_twist_reaches_the_counterparts_actual_request(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    twisted = await admin.post(f"/api/sessions/{session['id']}/twists", json={"text": "The river rises"})
    assert twisted.status_code == 200, twisted.text
    (record,) = [item for item in twisted.json()["state"]["injections"] if item["id"].startswith("free_")]
    rewritten = record["rewritten"]
    assert rewritten == "The situation shifts."  # the director's rewrite, not the trainer's original
    await say(bob, session["id"], "Hello.")
    counterpart = [call for call in model.requests if call.role == "counterpart"][-1]
    sent = json.dumps(counterpart.model_dump(mode="json"))
    assert rewritten in sent  # the payload the counterpart model gets must carry the instruction


async def test_a_twist_over_the_limit_is_refused_before_any_model_call(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    me = (await admin.get("/api/me")).json()
    limit(app, limit_user_tokens_per_day=1000)
    await spend(app, me, tokens_in=600, tokens_out=400)
    refused = await admin.post(f"/api/sessions/{session['id']}/twists", json={"text": "A twist"})
    assert refused.status_code == 429
    assert model.calls["director"] == 0 and model.calls["bias"] == 0


async def test_a_twist_over_a_thousand_characters_is_refused(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    refused = await admin.post(f"/api/sessions/{session['id']}/twists", json={"text": "x" * 1001})
    assert refused.status_code == 422


async def test_a_partial_bias_answer_is_retried_then_refused(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    model.answers["bias"] = ['{"reason": "cannot determine"}'] * 2  # no explicit verdict: malformed, not unflagged
    response = await admin.post(f"/api/sessions/{session['id']}/twists", json={"text": "The river rises"})
    assert response.status_code == 502, response.text
    assert model.calls["bias"] == 2  # retried once before giving up


async def test_a_blank_director_instruction_is_retried_then_refused(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    model.answers["director"] = ['{"instruction": "   "}'] * 2
    response = await admin.post(f"/api/sessions/{session['id']}/twists", json={"text": "The river rises"})
    assert response.status_code == 502, response.text
    assert model.calls["director"] == 2


async def test_a_watcher_comments_during_play_and_after_the_end(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    await say(bob, session["id"], "Hello.")
    posted = await admin.post(f"/api/sessions/{session['id']}/comments", json={"turn": 1, "text": "Good opener"})
    assert posted.status_code == 201, posted.text
    me = (await admin.get("/api/me")).json()
    progress = (await admin.get(f"/api/sessions/{session['id']}/progress")).json()
    (comment,) = progress["comments"]
    assert comment["turn"] == 1 and comment["text"] == "Good opener"
    assert comment["author"] == me["display_name"] and comment["created_at"]
    # and after the end
    assert (await bob.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    again = await admin.post(f"/api/sessions/{session['id']}/comments", json={"turn": 1, "text": "After the end"})
    assert again.status_code == 201
    # the player never sees comments: not in the session, the debrief, the list, and never posts one
    for response in (
        await bob.get(f"/api/sessions/{session['id']}"),
        await bob.get(f"/api/sessions/{session['id']}/debrief"),
        await bob.get("/api/sessions"),
    ):
        assert "Good opener" not in response.text
    assert (
        await bob.post(f"/api/sessions/{session['id']}/comments", json={"turn": 1, "text": "mine"})
    ).status_code == 403


async def test_a_comment_on_a_missing_turn_is_refused(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    response = await admin.post(f"/api/sessions/{session['id']}/comments", json={"turn": 99999, "text": "orphan note"})
    assert response.status_code == 422, response.text


async def test_a_watcher_sees_the_pinned_twists_goals_and_counterpart(app, new_client):
    use_model(app)
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    solo = await start_play(bob, (await bob.post("/api/scenarios", json={"content": draft()})).json()["id"])
    progress = (await admin.get(f"/api/sessions/{solo['id']}/progress")).json()
    assert "military_call" in {item["id"] for item in progress["injections"]}
    assert progress["outcomes"] and {"id", "label", "result", "when"} <= set(progress["outcomes"][0])
    assert progress["counterpart"] == draft()["counterparts"][0]["role"]
    assert progress["title"] == draft()["title"]
    assert progress["turn_running"] is False


async def test_a_turn_committed_during_the_director_call_survives_the_twist(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    gate, pending = await gated_twist(model, admin, session["id"])
    done = done_of(await asyncio.wait_for(say(bob, session["id"], "Hello."), timeout=10))
    assert done["turn"] == 1
    gate.set()
    response = await asyncio.wait_for(pending, timeout=10)
    assert response.status_code == 200, response.text
    assert response.json()["state"]["turn"] == 1  # the twist lands on turn 1's state, not the stale turn 0


async def test_an_override_set_during_the_director_call_survives_the_twist(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    gate, pending = await gated_twist(model, admin, session["id"])
    assert (await set_dial(admin, session["id"], 80)).status_code == 200
    gate.set()
    response = await asyncio.wait_for(pending, timeout=10)
    assert response.status_code == 200, response.text
    assert response.json()["state"]["dials"]["trust"] == 80  # not restored to the stale 35


async def test_a_turn_started_during_the_director_call_refuses_the_twist(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    gate, pending = await gated_twist(model, admin, session["id"])
    turn_gate = model.once["classifier"] = asyncio.Event()
    turn = asyncio.create_task(say(bob, session["id"], "Hello."))
    await asyncio.wait_for(model.entered["classifier"].wait(), timeout=10)  # the turn holds its claim
    gate.set()
    response = await asyncio.wait_for(pending, timeout=10)
    assert response.status_code == 409, response.text
    turn_gate.set()
    await asyncio.wait_for(turn, timeout=10)


async def test_an_end_during_the_director_call_refuses_the_twist(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    gate, pending = await gated_twist(model, admin, session["id"])
    assert (await bob.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await settle(app)
    gate.set()
    response = await asyncio.wait_for(pending, timeout=10)
    assert response.status_code == 410, response.text


async def test_paid_twist_calls_survive_a_refused_write(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    gate, pending = await gated_twist(model, admin, session["id"])
    gone = await bob.delete("/api/me")  # the session goes with the account: the twist's final write will be refused
    assert gone.status_code in (200, 204), gone.text
    bias_gate = model.once["bias"] = asyncio.Event()
    gate.set()
    await asyncio.wait_for(model.entered["bias"].wait(), timeout=10)
    # the director's paid row is already committed before the bias call
    assert ("director", "ok") in await ledger(app, session["id"])
    bias_gate.set()
    response = await asyncio.wait_for(pending, timeout=10)
    assert response.status_code == 404, response.text
    rows = await ledger(app, session["id"])
    assert ("director", "ok") in rows and ("bias", "ok") in rows, rows


async def test_a_bias_provider_failure_is_charged_to_the_bias_role_and_model(app, new_client):
    model = use_model(app)
    app.state.llm = (  # the two roles price differently, so the error's role and model both matter
        model,
        LLMConfig(
            default=RoleConfig(model="director-model", api_key=SecretStr("k"), first_word_seconds=0.5),
            roles={"bias": RoleConfig(model="bias-model", api_key=SecretStr("k"), first_word_seconds=0.5)},
        ),
    )
    admin, bob, session = await member_session(app, new_client)
    model.answers["bias"] = [RuntimeError("provider unavailable")]
    response = await admin.post(f"/api/sessions/{session['id']}/twists", json={"text": "The river rises"})
    assert response.status_code == 502
    async with app.state.sessionmaker() as db:
        rows = {
            (str(row.role), str(row.model), str(row.outcome))
            for row in (await db.execute(select(LlmCall).where(LlmCall.session_id == session["id"]))).scalars()
        }
    assert ("bias", "bias-model", "error") in rows, rows
    assert ("director", "director-model", "ok") in rows, rows
