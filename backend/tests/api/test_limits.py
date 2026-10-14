import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from nlab.db.auth_sessions import utcnow
from nlab.db.models import LlmCall, PlaySession
from nlab.db.usage import start_of_day, usage_since
from tests.api.support import (
    card_id,
    draft,
    join,
    org_with_admin,
    say,
    seed_curated,
    sign_in,
    start_play,
    use_model,
)
from tests.api.test_convert_api import CONFIG
from tests.llm.fakes import FakeProvider

pytestmark = pytest.mark.anyio


def limit(app, **changes):
    app.state.settings = app.state.settings.model_copy(update=changes)


async def spend(app, me, tokens_in=0, tokens_out=0, model="test-model", when=None, org=None):
    async with app.state.sessionmaker() as db:
        db.add(
            LlmCall(
                user_id=me["id"],
                org_id=org or me["active_org"]["id"],
                role="classifier",
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                outcome="ok",
                **({"created_at": when} if when else {}),
            )
        )
        await db.commit()


async def alice_with_scenario(app, new_client):
    await seed_curated(app)
    alice = new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    return alice, me, await card_id(alice, "camp")


async def test_the_session_limit_refuses_the_next_start(app, new_client):
    limit(app, limit_user_sessions_per_day=2)
    alice, _, scenario_id = await alice_with_scenario(app, new_client)
    await start_play(alice, scenario_id)
    await start_play(alice, scenario_id)
    refused = await alice.post("/api/sessions", json={"scenario_id": scenario_id})
    assert refused.status_code == 429 and "00:00 UTC" in refused.json()["detail"]


async def test_the_user_token_limit_refuses_a_turn_before_any_model_call(app, new_client):
    model = use_model(app)
    limit(app, limit_user_tokens_per_day=1000)
    alice, me, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    await spend(app, me, tokens_in=900, tokens_out=100)
    refused = await alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Hello."})
    assert refused.status_code == 429 and "practice limit" in refused.json()["detail"]
    assert sum(model.calls.values()) == 0
    assert (await alice.get(f"/api/sessions/{session['id']}")).json()["turn"] == 0  # nothing claimed or saved
    async with app.state.sessionmaker() as db:
        claim = await db.scalar(select(PlaySession.turn_in_progress).where(PlaySession.id == uuid.UUID(session["id"])))
    assert claim is None  # the refusal happened before any claim


async def test_yesterdays_use_does_not_count(app, new_client):
    use_model(app)
    limit(app, limit_user_tokens_per_day=100_000)
    alice, me, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    await spend(app, me, tokens_in=5_000_000, when=start_of_day(utcnow()) - timedelta(hours=1))  # yesterday, 23:00 UTC
    events = await say(alice, session["id"], "Hello.")
    assert any(event == "done" for event, _ in events)


async def test_the_org_limit_counts_the_orgs_total(app, new_client):
    use_model(app)
    limit(app, limit_org_tokens_per_day=1000, limit_user_tokens_per_day=0)
    alice, me, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    await spend(app, me, tokens_in=1000)  # the user limit is off: only the org's total can refuse
    refused = await alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Hello."})
    assert refused.status_code == 429 and "organisation" in refused.json()["detail"]


async def test_the_org_limit_counts_every_member(app, new_client):
    use_model(app)
    limit(app, limit_org_tokens_per_day=1000, limit_user_tokens_per_day=0)
    admin, _ = await org_with_admin(new_client)
    await seed_curated(app)
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    await join(alice, admin)
    session = await start_play(alice, await card_id(alice, "camp"))
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    bob_me = (await bob.get("/api/me")).json()  # after the join: bob's active org is the shared one
    await spend(app, bob_me, tokens_in=1000)  # another member's tokens count toward the shared org's total
    refused = await alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Hello."})
    assert refused.status_code == 429 and "organisation" in refused.json()["detail"]


async def test_limits_follow_the_user_across_orgs_and_playtests(app, new_client):
    alice = new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    created = await alice.post("/api/scenarios", json={"content": draft()})
    assert created.status_code == 201, created.text
    own = created.json()["id"]
    await start_play(alice, own, mode="playtest")  # playtests count toward the user's limits...
    limit(app, limit_user_sessions_per_day=1)
    refused = await alice.post("/api/sessions", json={"scenario_id": own, "mode": "playtest"})
    assert refused.status_code == 429  # ...and obey them
    admin, _ = await org_with_admin(new_client)
    await join(alice, admin)
    await seed_curated(app)
    refused = await alice.post("/api/sessions", json={"scenario_id": await card_id(alice, "camp")})
    assert refused.status_code == 429  # the user's count follows her into another org
    limit(app, limit_user_sessions_per_day=0, limit_user_tokens_per_day=10)
    await spend(app, me, tokens_in=10)  # spent in her personal org, still counts in the shared one
    model = use_model(app)
    refused = await alice.post("/api/scenarios/convert", json={"text": "# A\n\nA brief."})
    assert refused.status_code == 429
    assert sum(model.calls.values()) == 0


async def test_a_zero_session_limit_is_off(app, new_client):
    limit(app, limit_user_sessions_per_day=0)
    alice, _, scenario_id = await alice_with_scenario(app, new_client)
    await start_play(alice, scenario_id)
    await start_play(alice, scenario_id)  # 0 switches the limit off; it does not mean "no sessions"


async def test_a_debrief_is_skipped_with_a_clear_status_when_the_budget_is_gone(app, new_client):
    """Finding 4: ending never starts paid work after exhaustion and the end still returns 200. The admission-side
    contract lives in tests/api/test_budget.py."""
    model = use_model(app)
    alice, _, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    events = await asyncio.wait_for(say(alice, session["id"], "Hello."), timeout=10)
    assert any(event == "done" for event, _ in events)
    limit(app, daily_spend_ceiling_usd=0.000001, model_prices={"test-model": (1_000_000.0, 1_000_000.0)})  # over budget
    ended = await alice.post(f"/api/sessions/{session['id']}/end")
    assert ended.status_code == 200, ended.text
    await app.state.background.drain(timeout=10)
    debrief = (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()
    assert debrief["status"] == "failed"  # the paid debrief is skipped, and the status says so
    assert model.calls["debrief"] == 0


async def test_the_spend_ceiling_pauses_everyone(app, new_client):
    use_model(app)
    limit(app, daily_spend_ceiling_usd=1.0, model_prices={"pricey": (1_000_000.0, 0.0)})
    alice, me, scenario_id = await alice_with_scenario(app, new_client)
    bob = new_client()
    bob_me = await sign_in(bob, "bob", "bob@example.org")
    await spend(app, bob_me, tokens_in=1, model="pricey")  # 1 USD, spent by someone else
    refused = await alice.post("/api/sessions", json={"scenario_id": scenario_id})
    assert refused.status_code == 429 and "daily budget" in refused.json()["detail"]


async def test_a_zero_switches_a_limit_off(app, new_client):
    use_model(app)
    limit(app, limit_user_tokens_per_day=0, limit_org_tokens_per_day=0, daily_spend_ceiling_usd=0)
    alice, me, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    await spend(app, me, tokens_in=10**9)
    assert any(event == "done" for event, _ in await say(alice, session["id"], "Hello."))


async def test_brief_conversion_respects_the_limits(app, new_client):
    model = use_model(app)
    limit(app, limit_user_tokens_per_day=10)
    alice, me, _ = await alice_with_scenario(app, new_client)
    await spend(app, me, tokens_in=10)
    refused = await alice.post("/api/scenarios/convert", json={"text": "# A\n\nA brief."})
    assert refused.status_code == 429
    assert sum(model.calls.values()) == 0  # the refusal happened before any model call


async def test_conversion_retries_are_charged_before_next_conversion(app, new_client):
    """Every provider attempt of a conversion is reserved and charged: the next conversion meets an exhausted
    allowance instead of retrying for free."""
    alice = new_client()
    me = await sign_in(alice, "alice", "alice@example.org")
    provider = FakeProvider(["not json"] * 3)
    app.state.llm = (provider, CONFIG)
    first = await asyncio.wait_for(alice.post("/api/scenarios/convert", json={"text": "# A\n\nA brief."}), timeout=10)
    assert first.status_code == 200 and len(provider.requests) == 3  # the retries all ran
    async with app.state.sessionmaker() as db:
        charged = (await usage_since(db, start_of_day(utcnow()), {}, user_id=uuid.UUID(me["id"]))).tokens
    limit(app, limit_user_tokens_per_day=charged)  # exactly what the retries used: nothing is left
    second = await alice.post("/api/scenarios/convert", json={"text": "# A\n\nA brief."})
    assert second.status_code == 429 and len(provider.requests) == 3


def test_the_price_warning_names_the_painter_model(caplog):
    import logging

    from pydantic import SecretStr

    from nlab.api.limits import warn_about_prices
    from nlab.api.pictures import painter_from_env
    from nlab.api.settings import Settings
    from nlab.llm import LLMConfig, RoleConfig

    settings = Settings(
        _env_file=None,
        secret_key="s",
        daily_spend_ceiling_usd=1.0,
        model_prices={"chat-model": (1.0, 1.0)},
    )
    config = LLMConfig(default=RoleConfig(model="chat-model", api_key=SecretStr("k")))
    with caplog.at_level(logging.WARNING):
        warn_about_prices(settings, config, painter_from_env({}).model)
        warn_about_prices(settings, config, painter_from_env({"IMAGE_MODEL": "override-image"}).model)
    assert "gemini-3.1-flash-image" in caplog.text  # the default image model is named
    assert "override-image" in caplog.text  # and so is an IMAGE_MODEL override
