import pytest

from nlab.db.models import PlaySession, Turn
from tests.api.support import (
    PLAYER_SESSION_KEYS,
    card_id,
    count,
    draft,
    say,
    seed_curated,
    sign_in,
    start_play,
    use_model,
)

pytestmark = pytest.mark.anyio


async def test_starting_a_session_shows_the_opening_line_and_nothing_hidden(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    assert set(session) == PLAYER_SESSION_KEYS
    assert session["status"] == "active" and session["turn"] == 0 and session["outcome"] is None
    assert session["mode"] == "solo" and session["cover"] == "camp" and "objective" in session["brief"]
    assert [line["role"] for line in session["transcript"]] == ["character"]
    assert session["transcript"][0]["text"]
    assert await count(app, PlaySession) == 1 and await count(app, Turn) == 1


async def test_a_session_survives_a_closed_tab(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "checkpoint"))
    again = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert {**again, "seconds_left": 0} == {**session, "seconds_left": 0}  # the clock moves between the two reads


async def test_only_editors_may_playtest(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    refused = await alice.post("/api/sessions", json={"scenario_id": await card_id(alice, "camp"), "mode": "playtest"})
    assert refused.status_code == 403
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    assert (await start_play(alice, mine["id"], "playtest"))["mode"] == "playtest"


async def test_a_session_pins_its_version(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    session = await start_play(alice, mine["id"])
    changed = draft()
    changed["counterparts"][0]["opening"] = "A completely different opening."
    assert (await alice.put(f"/api/scenarios/{mine['id']}", json={"content": changed})).status_code == 200
    again = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert again["transcript"][0]["text"] == session["transcript"][0]["text"]


async def test_nobody_else_reads_a_session(app, new_client):
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    session = await start_play(alice, await card_id(alice, "camp"))
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    assert (await bob.get(f"/api/sessions/{session['id']}")).status_code == 404
    assert (await bob.get("/api/sessions")).json() == []


async def test_a_session_pins_its_brief_and_its_counterpart(app, new_client):
    use_model(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    old_objective = mine["content"]["trainee_brief"]["objective"].strip()
    old_persona = mine["content"]["counterparts"][0]["persona"].strip()
    session = await start_play(alice, mine["id"], "playtest")
    changed = draft()
    changed["title"] = "A completely different title."
    changed["trainee_brief"]["objective"] = "A completely different objective."
    changed["counterparts"][0]["persona"] = "A completely different persona."
    assert (await alice.put(f"/api/scenarios/{mine['id']}", json={"content": changed})).status_code == 200
    read = (await alice.get(f"/api/sessions/{session['id']}")).json()
    assert read["brief"]["objective"].strip() == old_objective  # the pinned version, not the edited one
    listed = (await alice.get("/api/sessions")).json()
    assert [card["title"] for card in listed] == [session["title"]]  # the list shows the pinned title too
    await say(alice, session["id"], "Hello.")
    progress = (await alice.get(f"/api/sessions/{session['id']}/progress")).json()
    frozen = progress["turns"][1]["counterpart_request"]["messages"][0]["content"]
    assert old_persona in frozen and "A completely different persona." not in frozen


async def test_session_pins_scenario_overrides(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    sc_draft = draft()
    sc_draft["overrides"] = {"moves": {"clarifies_operational_detail": {"deltas": {"trust": 15}}}}
    created = (await alice.post("/api/scenarios", json={"content": sc_draft})).json()
    session = await start_play(alice, created["id"], "playtest")
    import uuid

    async with app.state.sessionmaker() as db:
        ps = await db.get(PlaySession, uuid.UUID(session["id"]))
        assert ps.rules["moves"]["clarifies_operational_detail"]["deltas"]["trust"] == 15


async def test_session_starts_with_minimal_stakeholder_fields(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    sc_draft = draft()
    sc_draft["stakeholders"] = [
        {"id": "sh_1", "role": "Elder", "influence": "high"},
    ]
    created = (await alice.post("/api/scenarios", json={"content": sc_draft})).json()
    session = await start_play(alice, created["id"], "playtest")
    assert len(session["stakeholders"]) == 1
    sh = session["stakeholders"][0]
    assert sh["id"] == "sh_1"
    assert sh["role"] == "Elder"
    assert sh["persona"] == ""
    assert sh["influence"] == "high"
    assert sh["stance"] == "transformative"
    assert sh["scope"] == "local"


async def test_interlocutor_validation(app, new_client):
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    sc_draft = draft()
    sc_draft["stakeholders"] = [{"id": "sh_1", "role": "Elder"}]
    created = (await alice.post("/api/scenarios", json={"content": sc_draft})).json()
    session = await start_play(alice, created["id"], "playtest")

    # 1. Valid stakeholder ID returns 200
    res_ok = await alice.post(f"/api/sessions/{session['id']}/interlocutor", json={"interlocutor": "sh_1"})
    assert res_ok.status_code == 200
    assert res_ok.json()["active_interlocutor"] == "sh_1"

    # 2. Unknown interlocutor ID returns 400
    res_bad = await alice.post(
        f"/api/sessions/{session['id']}/interlocutor", json={"interlocutor": "nonexistent_target"}
    )
    assert res_bad.status_code == 400
    assert "Unknown interlocutor" in res_bad.json()["detail"]


async def test_a_deleted_scenario_leaves_no_painting_on_its_sessions(app, new_client):
    """A session outlives its scenario; once the painting is unreadable the thumbnail must fall back to a theme."""
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    mine = (await alice.post("/api/scenarios", json={"content": draft()})).json()
    webp = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 20  # enough magic: RIFF....WEBP
    assert (await alice.put(f"/api/scenarios/{mine['id']}/cover-image", content=webp)).status_code == 204
    await start_play(alice, mine["id"])
    before = (await alice.get("/api/sessions")).json()
    assert before[0]["cover"] == "custom" and before[0]["cover_image_version"]
    assert (await alice.delete(f"/api/scenarios/{mine['id']}")).status_code == 204
    after = (await alice.get("/api/sessions")).json()
    assert after[0]["cover_image_version"] is None
    assert (await alice.get(f"/api/scenarios/{mine['id']}/cover-image")).status_code == 404  # authorization unchanged
