"""A scenario's own pacing: how a silence is handled, which stages forbid twists, and a trainer deciding at time-out."""

from datetime import timedelta

import pytest
from sqlalchemy import update

from nlab.db.auth_sessions import utcnow
from nlab.db.models import PlaySession
from tests.api.support import draft, nudge, say, sign_in, start_play, use_model

pytestmark = pytest.mark.anyio


async def playtest(app, new_client, timing):
    """Alice's own scenario with `timing`, played as a playtest: she is the player and the steering trainer."""
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    content = draft()
    content["timing"] = timing
    made = await alice.post("/api/scenarios", json={"content": content})
    assert made.status_code == 201, made.text
    return alice, await start_play(alice, made.json()["id"], "playtest")


async def run_out_the_clock(app, session_id):
    async with app.state.sessionmaker() as db:
        await db.execute(
            update(PlaySession).where(PlaySession.id == session_id).values(created_at=utcnow() - timedelta(hours=3))
        )
        await db.commit()


async def test_a_scenarios_own_silence_rules_set_the_wait_the_line_and_the_penalty(app, new_client):
    model = use_model(app)
    alice, session = await playtest(
        app, new_client, {"silence": {"after_seconds": 30, "line": "Was there anything else?", "penalty": 12}}
    )
    assert session["silence_seconds"] == 30
    events = await nudge(alice, session["id"])
    assert ("reply", {"text": "Was there anything else?"}) in events  # the author's words, word for word
    assert model.calls["counterpart"] == 0  # no model call for them
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["transcript"][-1] == {
        "role": "character",
        "text": "Was there anything else?",
        "turn": 1,
        "speaker": "militia_rep",  # every line names its speaker now, single-party included
    }
    await alice.post(f"/api/sessions/{session['id']}/end")
    progress = (await alice.get(f"/api/sessions/{session['id']}/progress")).json()
    silence = [
        e for turn in progress["turns"] for e in turn["events"] if e.get("reason") == "Trainee silence / hesitation"
    ]
    assert [(e["dial"], e["after"] - e["before"]) for e in silence] == [("hostility", 12)]


async def test_without_silence_rules_the_built_in_ones_hold(app, new_client):
    model = use_model(app)
    model.replies.append(["Delegate, my time is limited."])
    alice, session = await playtest(app, new_client, {})
    assert session["silence_seconds"] == 90
    events = await nudge(alice, session["id"])
    assert ("reply", {"text": "Delegate, my time is limited."}) in events and model.calls["counterpart"] == 1
    progress = (await alice.get(f"/api/sessions/{session['id']}/progress")).json()
    silence = [
        e for turn in progress["turns"] for e in turn["events"] if e.get("reason") == "Trainee silence / hesitation"
    ]
    assert [(e["dial"], e["after"] - e["before"]) for e in silence] == [("hostility", 5)]


STAGES = {
    "phases": [
        {
            "id": "formalities",
            "label": "Formalities",
            "instruction": "Be formal.",
            "until_turn": 1,
            "allow_injects": False,
        },
        {"id": "the_ask", "instruction": "Press for terms."},
    ]
}


async def test_a_stage_that_forbids_twists_refuses_them_until_it_ends(app, new_client):
    model = use_model(app)
    alice, session = await playtest(app, new_client, STAGES)
    first = await alice.get(f"/api/sessions/{session['id']}/progress")
    assert first.json()["injects_allowed"] is False and first.json()["phase_label"] == "Formalities"
    refused = await alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    assert refused.status_code == 409 and "Formalities" in refused.json()["detail"]
    free = await alice.post(f"/api/sessions/{session['id']}/twists", json={"text": "A journalist arrives."})
    assert free.status_code == 409 and model.calls["director"] == 0  # refused before any paid call
    await say(alice, session["id"], "Good morning.")  # turn 1: still the first stage (it lasts up to turn 1)
    assert (
        await alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    ).status_code == 409
    await say(alice, session["id"], "May we talk about the convoy?")  # turn 2: the second stage
    allowed = await alice.post(f"/api/sessions/{session['id']}/inject", json={"injection_id": "military_call"})
    assert allowed.status_code == 200 and allowed.json()["injects_allowed"] is True


async def test_a_trainer_decides_how_a_meeting_ends_when_the_time_is_up(app, new_client):
    use_model(app)
    alice, session = await playtest(app, new_client, {"on_timeout": "trainer"})
    assert session["on_timeout"] == "trainer"
    path = f"/api/sessions/{session['id']}/time-decision"
    early = await alice.post(path, json={"result": "fail"})
    assert early.status_code == 409 and "time left" in early.json()["detail"]
    await run_out_the_clock(app, session["id"])
    progress = (await alice.get(f"/api/sessions/{session['id']}/progress")).json()
    assert progress["seconds_left"] == 0 and progress["on_timeout"] == "trainer"
    assert (await say(alice, session["id"], "Still talking."))[-1][0] == "done"  # nothing ends it by itself
    ended = await alice.post(path, json={"result": "fail"})
    assert ended.status_code == 200
    assert ended.json()["outcome"] == {"result": "fail", "label": "Time ran out without an agreement"}
    assert (await alice.post(path, json={"result": "ended"})).status_code == 410  # already ended


async def test_the_trainers_decision_is_for_scenarios_that_leave_it_to_them_and_for_watchers(app, new_client):
    use_model(app)
    alice, session = await playtest(app, new_client, {"on_timeout": "end"})
    await run_out_the_clock(app, session["id"])
    assert (
        await alice.post(f"/api/sessions/{session['id']}/time-decision", json={"result": "ended"})
    ).status_code == 409
    solo = await start_play(alice, (await alice.get(f"/api/sessions/{session['id']}")).json()["scenario_id"], "solo")
    # the player of a solo session never steers it, even in their own personal org
    assert (await alice.post(f"/api/sessions/{solo['id']}/time-decision", json={"result": "ended"})).status_code == 403
    assert (
        await alice.post(f"/api/sessions/{session['id']}/time-decision", json={"result": "nonsense"})
    ).status_code == 422
