import uuid

import pytest

from nlab.db.models import PlaySession
from tests.api.support import (
    card_id,
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


async def test_cchn_debrief_api_and_reflection(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client)
    session_id = session["id"]

    # Play two turns
    await say(alice, session_id, "I hear and acknowledge your frustration. What are your operational concerns?")
    await say(alice, session_id, "We propose sending three trucks along the agreed corridor.")

    # End session
    ended = await alice.post(f"/api/sessions/{session_id}/end")
    assert ended.status_code == 200
    await settle(app)

    # Get debrief
    resp = await alice.get(f"/api/sessions/{session_id}/debrief")
    assert resp.status_code == 200
    debrief = resp.json()
    assert debrief["status"] == "ready"
    assert "cchn_debrief" in debrief
    cchn = debrief["cchn_debrief"]
    assert cchn is not None
    assert "agreement_check" in cchn
    assert len(cchn["agreement_check"]["criteria"]) == 5
    assert "zones" in cchn
    assert cchn["zones"]["zone"] in ("E", "D", "F", "RED", "NO_DEAL")
    assert "level_timeline" in cchn
    assert len(cchn["level_timeline"]["entries"]) >= 2
    assert "iceberg_depth" in cchn
    assert len(cchn["iceberg_depth"]["layers"]) == 3
    assert "deescalation_report" in cchn
    assert "prep_vs_reality" in cchn
    assert "reflection" in cchn
    assert len(cchn["reflection"]["questions"]) == 3
    assert "competences" in cchn
    assert len(cchn["competences"]["tiers"]) == 3
    assert len(cchn["knowledge_links"]) == 8

    # Save reflection answers
    ref_body = {
        "answers": {
            "t6_counterpart_perspective": "We actively validated their concerns.",
            "t6_options_under_resistance": "We offered corridor options.",
            "t6_clear_next_steps": "We designated a liaison hotline.",
        }
    }
    put_ref = await alice.put(f"/api/sessions/{session_id}/reflection", json=ref_body)
    assert put_ref.status_code == 200
    updated_session = put_ref.json()
    assert updated_session["reflection"] == ref_body["answers"]

    # Re-fetch debrief to confirm reflection answers persist and reflect in CCHN debrief
    resp2 = await alice.get(f"/api/sessions/{session_id}/debrief")
    assert resp2.status_code == 200
    debrief2 = resp2.json()
    assert debrief2["reflection"] == ref_body["answers"]
    assert debrief2["cchn_debrief"]["reflection"]["completed"] is True
    assert debrief2["cchn_debrief"]["reflection"]["questions"][0]["answer"] == "We actively validated their concerns."


async def test_multiparty_debrief_shows_every_partys_dials(app, new_client):
    use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "tripartite"))
    session_id = session["id"]

    await say(alice, session_id, "Colonel, we ask for safe passage of the convoy.")
    ended = await alice.post(f"/api/sessions/{session_id}/end")
    assert ended.status_code == 200
    await settle(app)

    debrief = (await alice.get(f"/api/sessions/{session_id}/debrief")).json()
    per_party = debrief["counterpart_dials"]
    assert per_party is not None
    by_id = {party["id"]: party for party in per_party}
    assert set(by_id) == {"gov_colonel", "opposition_cmdr"}  # the sheikh was never engaged: not listed
    assert by_id["gov_colonel"]["role"] == "Government Sector Commander (Col. Bashir)"  # the scenario's role string
    assert set(by_id["gov_colonel"]["dials"]) >= {"trust", "rigidity", "hostility"}

    # once the sheikh is actually engaged, his dials appear too — in a fresh session
    session2 = await start_play(alice, await card_id(alice, "tripartite"))
    sid2 = session2["id"]
    switched = await alice.post(f"/api/sessions/{sid2}/interlocutor", json={"interlocutor": "sheikh_khalil"})
    assert switched.status_code == 200
    await say(alice, sid2, "Sheikh, the town needs the convoy.")
    await alice.post(f"/api/sessions/{sid2}/end")
    await settle(app)
    debrief2 = (await alice.get(f"/api/sessions/{sid2}/debrief")).json()
    by_id2 = {party["id"]: party for party in debrief2["counterpart_dials"]}
    assert "sheikh_khalil" in by_id2 and "icrc" not in " ".join(by_id2)


async def test_single_counterpart_debrief_has_no_per_party_dials(app, new_client):
    use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    cards = (await alice.get("/api/scenarios")).json()
    imn = next(card["id"] for card in cards if card["title"] == "IMN Detainee Access via Network Mapping")
    session = await start_play(alice, imn)  # one commander plus two stakeholders
    ended = await alice.post(f"/api/sessions/{session['id']}/end")
    assert ended.status_code == 200
    await settle(app)

    debrief = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert debrief["counterpart_dials"] is None  # stakeholders were never engaged


async def test_single_party_debrief_has_no_per_party_dials(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client)
    ended = await alice.post(f"/api/sessions/{session['id']}/end")
    assert ended.status_code == 200
    await settle(app)

    debrief = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert debrief["counterpart_dials"] is None


async def test_reflection_waits_for_the_session_to_end(app, new_client):
    use_model(app)
    alice, session = await playing(app, new_client)
    session_id = session["id"]

    early = await alice.put(f"/api/sessions/{session_id}/reflection", json={"answers": {"q": "too soon"}})
    assert early.status_code == 410

    ended = await alice.post(f"/api/sessions/{session_id}/end")
    assert ended.status_code == 200
    saved = await alice.put(f"/api/sessions/{session_id}/reflection", json={"answers": {"q": "afterwards"}})
    assert saved.status_code == 200


async def test_debrief_dials_follow_the_counterpart_when_a_stakeholder_is_selected(app, new_client):
    use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    cards = (await alice.get("/api/scenarios")).json()
    imn = next(card["id"] for card in cards if card["title"] == "IMN Detainee Access via Network Mapping")
    session = await start_play(alice, imn)
    session_id = session["id"]

    # two constructive turns with the commander move HIS dials (whatever the scripted model classifies)
    await say(alice, session_id, "I hear and acknowledge your frustration. What are your operational concerns?")
    await say(alice, session_id, "What would a safe visit look like for your detainees?")
    async with app.state.sessionmaker() as db:  # Jibril's entry ends clearly off the baseline
        row = await db.get_one(PlaySession, uuid.UUID(session_id))
        engine_state = dict(row.engine_state)
        engine_state["counterpart_dials"]["commander_jibril"] = {
            **engine_state["counterpart_dials"]["commander_jibril"],
            "trust": 62,
            "rigidity": 49,
            "hostility": 29,
        }
        engine_state["dials"] = dict(engine_state["counterpart_dials"]["commander_jibril"])
        row.engine_state = engine_state
        await db.commit()
    # select a stakeholder, say nothing, end
    switched = await alice.post(f"/api/sessions/{session_id}/interlocutor", json={"interlocutor": "sheikh_zubair"})
    assert switched.status_code == 200
    await alice.post(f"/api/sessions/{session_id}/end")
    await settle(app)

    debrief = (await alice.get(f"/api/sessions/{session_id}/debrief")).json()
    assert debrief["counterpart_dials"] is None  # one qualifying party, so no per-party list
    # Jibril's dials, not the scenario baseline the never-engaged sheikh holds
    assert debrief["dials"] == {"trust": 62, "rigidity": 49, "hostility": 29, "consistency": 100}
