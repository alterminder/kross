"""Guest play: an anonymous visitor starts at once, plays curated scenarios alone, and is held to its own daily caps."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from nlab.api.deps import GUEST_ALLOWED
from nlab.db.accounts import purge_guests
from nlab.db.auth_sessions import utcnow
from nlab.db.models import Org, PlaySession, User
from nlab.db.usage import start_of_day
from tests.api.support import card_id, count, say, seed_curated, sign_in, start_play, use_model
from tests.api.test_limits import limit, spend

pytestmark = pytest.mark.anyio


async def guest(app, new_client):
    limit(app, guest_play=True)
    client = new_client()
    started = await client.post("/api/auth/guest")
    assert started.status_code == 204, started.text
    me = (await client.get("/api/me")).json()
    return client, me


async def test_guest_play_is_off_until_the_operator_turns_it_on(app, new_client):
    client = new_client()
    assert (await client.get("/api/auth/guest")).json() == {"enabled": False}
    assert (await client.post("/api/auth/guest")).status_code == 404
    assert await count(app, User) == 0
    limit(app, guest_play=True)
    assert (await client.get("/api/auth/guest")).json() == {"enabled": True}


async def test_a_guest_starts_at_once_and_plays_a_curated_scenario(app, new_client):
    use_model(app)
    await seed_curated(app)
    client, me = await guest(app, new_client)
    assert me["is_guest"] and me["email"] is None and me["active_org"]["personal"]
    cards = (await client.get("/api/scenarios")).json()
    assert cards and all(not card["can_edit"] for card in cards)
    session = await start_play(client, await card_id(client, "camp"))
    assert session["mode"] == "solo"
    assert [event for event, _ in await say(client, session["id"], "Good morning.")][-1] == "done"
    assert (await client.post(f"/api/sessions/{session['id']}/end")).status_code == 200


async def test_a_guest_can_do_nothing_beyond_playing(app, new_client):
    await seed_curated(app)
    client, me = await guest(app, new_client)
    scenario = await card_id(client, "camp")
    closed = [
        ("POST", "/api/scenarios", {"content": {}}),
        ("POST", "/api/scenarios/validate", {"content": {}}),
        ("POST", "/api/scenarios/convert", {"text": "a brief"}),  # a model call: never for a guest
        ("POST", f"/api/scenarios/{scenario}/duplicate", None),
        ("DELETE", f"/api/scenarios/{scenario}", None),
        ("DELETE", "/api/me", None),
        ("POST", "/api/orgs", {"name": "x"}),
        ("POST", "/api/orgs/active", {"org_id": me["active_org"]["id"]}),
        ("GET", "/api/org", None),
        ("POST", "/api/org/invites", {}),
        ("GET", "/api/rules", None),
        ("GET", "/api/admin/usage", None),
    ]
    for method, path, body in closed:
        response = await client.request(method, path, json=body)
        assert response.status_code in (403, 404, 405), (method, path, response.status_code)
        assert response.status_code != 404 or path.startswith("/api/org"), (method, path)
    assert (await client.post("/api/sessions", json={"scenario_id": scenario, "mode": "playtest"})).status_code == 403
    assert await count(app, Org) == 2  # the guest's personal space and the system org: POST /api/orgs made nothing


async def test_a_guest_cannot_see_the_progress_of_its_own_session(app, new_client):
    use_model(app)
    await seed_curated(app)
    client, _ = await guest(app, new_client)
    session = await start_play(client, await card_id(client, "camp"))
    for path in ("progress", "dials", "twists", "comments"):
        assert (await client.request("GET", f"/api/sessions/{session['id']}/{path}")).status_code in (403, 405)


async def test_every_guest_route_is_listed_in_the_allowlist():
    for method, path in GUEST_ALLOWED:
        assert method in ("GET", "POST", "PUT") and path.startswith("/api/")


async def test_a_guest_has_its_own_daily_caps(app, new_client):
    use_model(app)
    await seed_curated(app)
    client, me = await guest(app, new_client)
    limit(app, guest_limit_sessions_per_day=2, guest_limit_tokens_per_day=1000)
    scenario = await card_id(client, "camp")
    await start_play(client, scenario)
    await start_play(client, scenario)
    third = await client.post("/api/sessions", json={"scenario_id": scenario, "mode": "solo"})
    assert third.status_code == 429 and "Guests can start only a few sessions" in third.json()["detail"]
    await spend(app, me, tokens_in=900, tokens_out=200)
    over = await client.post("/api/sessions", json={"scenario_id": scenario, "mode": "solo"})
    assert over.status_code == 429 and "guest practice limit" in over.json()["detail"]
    # the caps are the guest's: a signed-in user is not held to them
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.post("/api/sessions", json={"scenario_id": scenario, "mode": "solo"})).status_code == 201


async def test_all_guests_together_share_one_daily_budget(app, new_client):
    use_model(app)
    await seed_curated(app)
    first, me = await guest(app, new_client)
    second, _ = await guest(app, new_client)
    limit(app, guest_limit_total_tokens_per_day=5000)
    scenario = await card_id(first, "camp")
    await spend(app, me, tokens_in=5000)  # the first guest alone uses the whole budget
    refused = await second.post("/api/sessions", json={"scenario_id": scenario, "mode": "solo"})
    assert refused.status_code == 429 and "Guest practice is full for today" in refused.json()["detail"]
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert (await alice.post("/api/sessions", json={"scenario_id": scenario, "mode": "solo"})).status_code == 201


async def test_new_guests_are_capped_each_day(app, new_client):
    limit(app, guest_play=True, guest_limit_signups_per_day=2)
    for _ in range(2):
        assert (await new_client().post("/api/auth/guest")).status_code == 204
    full = await new_client().post("/api/auth/guest")
    assert full.status_code == 429 and "Guest practice is full for today" in full.json()["detail"]
    assert await count(app, User) == 2


async def test_an_active_guest_cookie_reuses_the_same_guest(app, new_client):
    """Finding 17: a browser that already has a live guest is never handed a second account."""
    client, me = await guest(app, new_client)
    again = await client.post("/api/auth/guest")
    assert again.status_code == 204
    assert (await client.get("/api/me")).json()["id"] == me["id"]
    assert await count(app, User) == 1


async def test_a_reused_guest_cookie_spends_no_signup_quota(app, new_client):
    """The reuse short-circuits before signup admission: one visitor cannot burn the shared quota by repeating
    the request from the same browser."""
    limit(app, guest_play=True, guest_limit_signups_per_day=1)
    client = new_client()
    assert (await client.post("/api/auth/guest")).status_code == 204  # the one signup for today
    assert (await client.post("/api/auth/guest")).status_code == 204  # the same browser: no new signup
    assert (await new_client().post("/api/auth/guest")).status_code == 429  # a new visitor still finds it full
    assert await count(app, User) == 1


async def test_a_guest_session_ends_with_its_short_lifetime(app, new_client):
    limit(app, guest_play=True, guest_session_hours=2)
    client = new_client()
    response = await client.post("/api/auth/guest")
    assert "Max-Age=7200" in response.headers["set-cookie"]


async def test_old_guests_are_purged_and_real_users_never(app, new_client):
    use_model(app)
    await seed_curated(app)
    client, me = await guest(app, new_client)
    await start_play(client, await card_id(client, "camp"))
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    cutoff = start_of_day(utcnow()) - timedelta(days=1)
    async with app.state.sessionmaker() as db:
        assert await purge_guests(db, cutoff) == 0  # today's guest stays
        user = await db.get_one(User, me["id"])
        user.created_at = cutoff - timedelta(hours=1)
        await db.commit()
    async with app.state.sessionmaker() as db:
        assert await purge_guests(db, cutoff) == 1
        await db.commit()
    assert await count(app, PlaySession) == 0  # the guest's sessions went with it
    async with app.state.sessionmaker() as db:
        assert (await db.scalars(select(User.is_guest))).all() == [False]
        assert len((await db.scalars(select(Org.id))).all()) == 1 + 1  # alice's personal org, and the system org
