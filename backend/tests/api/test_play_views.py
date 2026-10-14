import json

import pytest

from nlab.db.models import PlaySession
from tests.api.support import (
    card_id,
    count,
    draft,
    join,
    org_with_admin,
    say,
    seed_curated,
    settle,
    sign_in,
    start_play,
    use_model,
)

pytestmark = pytest.mark.anyio


async def member_session(app, new_client):
    await seed_curated(app)
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    session = await start_play(bob, await card_id(bob, "camp"))
    return admin, bob, session


async def test_the_player_never_sees_progress_in_solo_play(app, new_client):
    use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")  # admin of her personal org
    session = await start_play(alice, await card_id(alice, "camp"))
    await say(alice, session["id"], "Hello.")
    assert (await alice.get(f"/api/sessions/{session['id']}/progress")).status_code == 403


async def test_the_player_deletes_their_own_session(app, new_client):
    use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    await say(alice, session["id"], "Hello.")
    assert (await alice.delete(f"/api/sessions/{session['id']}")).status_code == 204
    assert (await alice.get(f"/api/sessions/{session['id']}")).status_code == 404
    assert await count(app, PlaySession) == 0


async def test_a_stranger_cannot_delete_another_players_session(app, new_client):
    use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    assert (await bob.delete(f"/api/sessions/{session['id']}")).status_code == 404
    assert await count(app, PlaySession) == 1


async def test_watch_reads_the_pinned_twists_of_a_private_unsubmitted_scenario(app, new_client):
    """New decision (Plan H, 2026-10-01): a steering admin sees the pinned version's preset twists, even on a
    member's private scenario — the invite notice says admins can see and steer. This replaces PR #7's decision
    that a solo watcher never sees unused twist labels."""
    use_model(app)
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    content = draft()
    secret = "Unreleased plan: evacuate site Delta"
    content["injections"] = [{"id": "unreleased", "label": secret, "instruction": "Mention the plan."}]
    scenario = (await bob.post("/api/scenarios", json={"content": content})).json()
    solo = await start_play(bob, scenario["id"])
    assert (await admin.get(f"/api/scenarios/{scenario['id']}")).status_code == 404
    response = await admin.get(f"/api/sessions/{solo['id']}/progress")
    assert response.status_code == 200
    assert response.json()["injections"] == [{"id": "unreleased", "label": secret}]
    assert response.json()["state"]["injections"] == []


async def test_an_admin_watches_a_members_session_turn_by_turn(app, new_client):
    model = use_model(app)
    model.answers["classifier"].append(
        json.dumps({"moves": [{"id": "shows_respect_curiosity", "quote": "I hear you"}]})
    )
    admin, bob, session = await member_session(app, new_client)
    await say(bob, session["id"], "I hear you.")
    await settle(app)
    progress = (await admin.get(f"/api/sessions/{session['id']}/progress")).json()
    assert progress["player"] == "bob" and progress["status"] == "active"
    assert [turn["number"] for turn in progress["turns"]] == [0, 1]
    turn = progress["turns"][1]
    assert turn["trainee_text"] == "I hear you." and "trust" in turn["dials"]
    assert any(event["kind"] == "dial" for event in turn["events"]) and turn["scores"] is not None
    assert turn["counterpart_request"]["role"] == "counterpart"
    assert (await bob.get(f"/api/sessions/{session['id']}/progress")).status_code == 403


async def test_other_orgs_and_other_members_see_nothing(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    other_admin, _ = await org_with_admin(new_client, "Org B")
    assert (await other_admin.get(f"/api/sessions/{session['id']}/progress")).status_code == 404
    carol = new_client()
    await sign_in(carol, "carol", "carol@example.org")
    await join(carol, admin)
    assert (await carol.get(f"/api/sessions/{session['id']}")).status_code == 404
    assert (await carol.get(f"/api/sessions/{session['id']}/progress")).status_code == 404


async def test_the_org_list_identifies_the_player_by_id(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    bob_id = (await bob.get("/api/me")).json()["id"]
    listed = (await admin.get("/api/sessions?scope=org")).json()
    assert [(item["id"], item["player_id"]) for item in listed] == [(session["id"], bob_id)]
    mine = (await bob.get("/api/sessions")).json()
    assert [item["player_id"] for item in mine] == [None]


async def test_admins_list_the_orgs_solo_sessions_only(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    listed = (await admin.get("/api/sessions?scope=org")).json()
    assert [(item["id"], item["player"]) for item in listed] == [(session["id"], "bob")]
    assert (await bob.get("/api/sessions?scope=org")).status_code == 403
    assert [item["id"] for item in (await bob.get("/api/sessions")).json()] == [session["id"]]


async def test_rules_are_pinned_at_start(app, new_client):
    model = use_model(app)
    admin, bob, session = await member_session(app, new_client)
    await admin.put("/api/rules", json={"moves": {"evades_direct_question": {"trust": -20}}})
    model.answers["classifier"].append(json.dumps({"moves": [{"id": "evades_direct_question", "quote": "Maybe"}]}))
    await say(bob, session["id"], "Maybe.")
    progress = (await admin.get(f"/api/sessions/{session['id']}/progress")).json()
    before, after = progress["turns"][0]["dials"]["trust"], progress["turns"][1]["dials"]["trust"]
    assert before - after == 3  # the default at start, not the admin's later -20


async def test_account_deletion_removes_the_players_sessions(app, new_client):
    use_model(app)
    admin, bob, session = await member_session(app, new_client)
    assert (await bob.delete("/api/me")).status_code == 204
    assert await count(app, PlaySession) == 0


async def test_rule_edits_made_before_the_start_apply(app, new_client):
    model = use_model(app)
    await seed_curated(app)
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    assert (
        await admin.put("/api/rules", json={"moves": {"evades_direct_question": {"trust": -20}}})
    ).status_code == 200
    session = await start_play(bob, await card_id(bob, "camp"))
    model.answers["classifier"].append(json.dumps({"moves": [{"id": "evades_direct_question", "quote": "Maybe"}]}))
    await say(bob, session["id"], "Maybe.")
    progress = (await admin.get(f"/api/sessions/{session['id']}/progress")).json()
    before, after = progress["turns"][0]["dials"]["trust"], progress["turns"][1]["dials"]["trust"]
    assert before - after == 20  # the edit made before the start, pinned into the session


async def test_an_active_session_reports_what_is_left_of_the_scenarios_minutes(app, new_client):
    from datetime import timedelta

    from sqlalchemy import update

    from nlab.db.auth_sessions import utcnow

    use_model(app)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))  # the camp scenario is 20 minutes
    assert session["minutes_total"] == 20 and 1190 <= session["seconds_left"] <= 1200
    async with app.state.sessionmaker() as db:
        await db.execute(
            update(PlaySession)
            .where(PlaySession.id == session["id"])
            .values(created_at=utcnow() - timedelta(minutes=19))
        )
        await db.commit()
    nearly = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert 55 <= nearly["seconds_left"] <= 60
    async with app.state.sessionmaker() as db:
        await db.execute(
            update(PlaySession).where(PlaySession.id == session["id"]).values(created_at=utcnow() - timedelta(hours=2))
        )
        await db.commit()
    assert (await alice.get(f"/api/sessions/{session['id']}")).json()["seconds_left"] == 0  # never negative
    ended = (await alice.post(f"/api/sessions/{session['id']}/end")).json()
    assert ended["minutes_total"] == 20 and ended["seconds_left"] is None
