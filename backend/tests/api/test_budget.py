"""Paid-work admission: a conservative reservation before every billed
provider call, exact-id durable settlement, durable daily admissions that survive deletion, and bounded
background work. The concurrency tests drive the real budget guard and the real HTTP API against real Postgres."""

import asyncio
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from nlab.db.auth_sessions import utcnow
from nlab.db.models import BudgetReservation
from nlab.db.usage import start_of_day, usage_since
from nlab.llm.config import RoleConfig
from nlab.llm.types import AdmissionDenied, Completion, Request, Usage
from tests.api.support import (
    card_id,
    join,
    org_with_admin,
    say,
    seed_curated,
    settle,
    sign_in,
    start_play,
    use_model,
)
from tests.api.test_limits import alice_with_scenario, limit

pytestmark = pytest.mark.anyio

SMALL = RoleConfig(model="test-model", api_key=SecretStr("k"), max_input_tokens=1000, max_output_tokens=2048)


def tiny_request(content: str = "hi") -> Request:
    return Request(
        role="classifier", model="test-model", messages=[{"role": "user", "content": content}], temperature=0
    )


class UsageFake:
    """A provider whose calls report the given usages in order; Usage(known=False) is a provider that reported no
    usage at all (never the same as a known zero)."""

    def __init__(self, *usages: Usage) -> None:
        self.usages = list(usages)
        self.calls = 0

    async def complete(self, config, request, schema=None, json=False):
        self.calls += 1
        return Completion("ok", "stop", self.usages.pop(0) if self.usages else Usage(10, 5))


class SDKUsage:
    """chat.completions shaped like the OpenAI SDK: usage is an object with token count attributes."""

    def __init__(self, usage) -> None:
        self.usage, self.calls = usage, 0

    async def create(self, **kwargs):
        self.calls += 1
        message = SimpleNamespace(content="ok", finish_reason="stop")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=self.usage)


async def open_soon(gate: asyncio.Event, seconds: float = 1.5) -> None:
    """Lets the one admitted call finish after the refused ones have answered."""
    await asyncio.sleep(seconds)
    gate.set()


def guard_for(app, provider, user_id=None, org_id=None):
    from nlab.api.budget import Actor, Budgeted

    actor = Actor(user_id or uuid.uuid4(), org_id or uuid.uuid4())
    return Budgeted(provider, app.state.sessionmaker, actor, lambda: app.state.settings), actor


def counted(app, user_id):
    async def read() -> int:
        async with app.state.sessionmaker() as db:
            usage = await usage_since(db, start_of_day(utcnow()), app.state.settings.model_prices, user_id=user_id)
        return usage.tokens

    return read()


async def test_only_one_overlapping_call_fits_under_the_cap(app):
    """Finding 2's probe at the enforcement boundary: eight overlapping paid calls under a 4000-token cap admit
    exactly one underlying provider call, and the pending charge never exceeds the cap."""
    from tests.api.fakes import ScriptedModel

    model = ScriptedModel()
    model.gates["classifier"] = asyncio.Event()  # the one admitted call parks here, so all eight overlap
    limit(app, limit_user_tokens_per_day=4000, max_concurrent_model_calls=8, max_concurrent_paid_per_user=8)
    guard, actor = guard_for(app, model)
    tasks = [asyncio.create_task(guard.complete(SMALL, tiny_request())) for _ in range(8)]
    try:
        await asyncio.wait_for(model.entered["classifier"].wait(), timeout=5)
        await asyncio.sleep(0.2)  # the refusals settle while the one admitted call is still gated
        assert model.calls["classifier"] == 1  # one underlying provider call, whatever the interleaving
        assert 0 < await counted(app, actor.user_id) <= 4000  # the cap as a literal: pending usage never exceeds it
    finally:
        model.gates["classifier"].set()  # never leave the admitted call (or the tasks) hanging
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert sum(isinstance(result, AdmissionDenied) for result in results) == 7
    assert model.calls["classifier"] == 1


async def test_the_per_account_in_flight_cap_refuses_the_second_call(app):
    """Finding 2: paid requests per account are bounded even when the budget would allow both."""
    from tests.api.fakes import ScriptedModel

    model = ScriptedModel()
    model.gates["classifier"] = asyncio.Event()
    limit(app, max_concurrent_paid_per_user=1, max_concurrent_model_calls=8)
    guard, _ = guard_for(app, model)
    first = asyncio.create_task(guard.complete(SMALL, tiny_request()))
    try:
        await asyncio.wait_for(model.entered["classifier"].wait(), timeout=5)
        with pytest.raises(AdmissionDenied, match="busy"):
            await guard.complete(SMALL, tiny_request())
    finally:
        model.gates["classifier"].set()
    await first


async def test_a_settled_call_counts_once_and_unknown_usage_keeps_its_full_charge(app):
    """The accounting contract: a settled call is counted exactly once (its actual usage) and a call whose usage
    the provider never reported keeps its full reserved charge."""
    user_id = uuid.uuid4()
    guard, actor = guard_for(app, UsageFake(Usage(10, 5), Usage(known=False)), user_id=user_id)
    await guard.complete(SMALL, tiny_request())
    assert await counted(app, user_id) == 15  # settled: the actual usage, counted once, never doubled
    await guard.complete(SMALL, tiny_request())
    assert await counted(app, user_id) > 15 + 2000  # the unknown call keeps its full reserved charge


GUARD = RoleConfig(model="review", api_key=SecretStr("k"), max_output_tokens=100)


@pytest.mark.parametrize(
    ("raw", "settled"),
    [
        pytest.param(SimpleNamespace(prompt_tokens=100, completion_tokens=None), None, id="null-completion-count"),
        pytest.param(SimpleNamespace(prompt_tokens=100), None, id="missing-completion-count"),
        pytest.param(SimpleNamespace(prompt_tokens=None, completion_tokens=None), None, id="both-counts-null"),
        pytest.param(SimpleNamespace(prompt_tokens=0, completion_tokens=0), (0, 0), id="known-zero-settles"),
        pytest.param(SimpleNamespace(prompt_tokens=100, completion_tokens=30), (100, 30), id="valid-usage-settles"),
    ],
)
async def test_partial_sdk_usage_never_releases_the_paid_reservation(app, raw, settled):
    """R1 at the enforcement boundary (OpenAICompatibleProvider + real Postgres): partial or null SDK usage
    understates nothing — the full hold stays open, so a second invocation is refused at the 350-token cap before a
    second SDK call. Complete usage settles the reservation exactly."""
    from nlab.llm.openai_compat import OpenAICompatibleProvider
    from tests.llm.fakes import fake_client

    sdk = SDKUsage(raw)
    guard, _ = guard_for(app, OpenAICompatibleProvider(lambda config: fake_client(sdk)), user_id=uuid.uuid4())
    limit(app, limit_user_tokens_per_day=350)  # one 217-token reservation fits; two never do
    request = Request(
        role="classifier",
        model="review",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0,
        max_tokens=100,
    )
    first = await guard.complete(GUARD, request)
    async with app.state.sessionmaker() as db:
        row = await db.get_one(BudgetReservation, first.usage.reservation_ids[0])
    assert first.usage.reservation_ids == (row.id,)  # provenance survives the parse
    if settled is None:
        assert row.state == "open"
        with pytest.raises(AdmissionDenied):
            await guard.complete(GUARD, request)
        assert sdk.calls == 1  # refused before the provider was called again
    else:
        assert (row.state, row.used_in, row.used_out) == ("settled", *settled)


async def test_malformed_counts_with_an_explicit_known_flag_still_keep_the_hold(app):
    """A caller that marks usage known (the painter boundary reads counts from an external API) must not clear a
    hold with counts that are not real nonnegative token counts."""
    guard, _ = guard_for(app, UsageFake(Usage(-5, 3, known=True)), user_id=uuid.uuid4())
    limit(app, limit_user_tokens_per_day=350)
    await guard.complete(GUARD, tiny_request("Hello"))
    with pytest.raises(AdmissionDenied):
        await guard.complete(GUARD, tiny_request("Hello"))


async def test_a_small_known_call_cannot_release_a_large_unknown_hold(app):
    """Exact-id settlement (the A/B counterexample): the large unknown call's hold must survive the small known
    call's settlement, or the large charge would silently vanish."""
    user_id = uuid.uuid4()
    guard, _ = guard_for(app, UsageFake(Usage(known=False), Usage(20, 0)), user_id=user_id)
    await guard.complete(SMALL, tiny_request("x" * 400))  # the large call: no usage reported, hold stays open
    await guard.complete(SMALL, tiny_request("hi"))  # the small known call: settles exactly its own reservation
    async with app.state.sessionmaker() as db:
        holds = (
            await db.execute(
                select(BudgetReservation.reserved_in, BudgetReservation.reserved_out, BudgetReservation.state)
                .where(BudgetReservation.user_id == user_id)
                .order_by(BudgetReservation.reserved_in.desc())
            )
        ).all()
    large, small = holds[0], holds[1]
    assert large.state == "open" and small.state == "settled"
    assert await counted(app, user_id) == large.reserved_in + large.reserved_out + 20  # the large hold is still charged


async def test_eight_parallel_turns_are_all_refused_under_a_one_token_cap(app, new_client):
    """The audit probe at the HTTP level: simultaneous requests must not all see 'no completed usage' and proceed."""
    model = use_model(app)
    limit(app, limit_user_tokens_per_day=1)
    alice, _, scenario_id = await alice_with_scenario(app, new_client)
    sessions = [await start_play(alice, scenario_id) for _ in range(3)]
    results = await asyncio.gather(
        *[alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Hello."}) for session in sessions]
    )
    assert sum(model.calls.values()) == 0  # no request reached the model
    for response in results:
        assert response.status_code in (200, 429)
        assert "event: done" not in response.text  # every stream ends in a quota refusal, not a finished turn


async def test_a_turn_the_guard_refuses_reaches_no_model_call(app, new_client):
    """The guard is wired into the turn pipeline: a quota refusal is a quota error, never a model failure."""
    model = use_model(app)
    alice, _, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    limit(app, limit_user_tokens_per_day=100)  # the pre-check passes; the call's bounded worst case does not fit
    events = await say(alice, session["id"], "Hello.")
    assert events[-1][0] == "error" and "practice limit" in events[-1][1]["detail"]
    assert sum(model.calls.values()) == 0
    claim = await _session_claim(app, session["id"])
    assert claim is None  # the refused turn released its claim and saved nothing


async def test_deleting_a_session_does_not_restore_todays_start_allowance(app, new_client):
    """Finding 8: start -> delete -> start must not replenish the daily session allowance."""
    limit(app, limit_user_sessions_per_day=1)
    alice, _, scenario_id = await alice_with_scenario(app, new_client)
    first = await start_play(alice, scenario_id)
    assert (await alice.delete(f"/api/sessions/{first['id']}")).status_code == 204
    refused = await alice.post("/api/sessions", json={"scenario_id": scenario_id})
    assert refused.status_code == 429


async def test_ending_after_the_cap_spends_nothing_and_returns_200(app, new_client):
    """Finding 4's probe: ending a session never starts paid work once the allowance is gone (the end stays 200)."""
    model = use_model(app)
    alice, _, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    await asyncio.wait_for(say(alice, session["id"], "Hello."), timeout=10)
    await settle(app)
    limit(app, daily_spend_ceiling_usd=0.000001, model_prices={"test-model": (1_000_000.0, 1_000_000.0)})  # over budget
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await settle(app)
    assert (await alice.get(f"/api/sessions/{session['id']}/debrief")).json()["status"] == "failed"
    assert model.calls["debrief"] == 0  # nothing billed after exhaustion; the scoring admitted earlier still counts
    assert model.calls["evaluator"] == 1


async def test_a_call_that_reports_no_usage_stays_charged_conservatively(app, new_client):
    """A provider failure with unknown usage must never be priced at zero (findings 3 and 4)."""
    model = use_model(app)
    alice, me, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    model.answers["classifier"].append(RuntimeError("provider down"))  # no usage reaches the ledger
    events = await say(alice, session["id"], "Hello.")
    assert events[-1][0] == "error"
    assert await counted(app, uuid.UUID(me["id"])) > 0  # the interrupted call stays conservatively charged
    limit(app, limit_user_tokens_per_day=1)
    refused = await alice.post(f"/api/sessions/{session['id']}/turns", json={"text": "Again."})
    assert refused.status_code == 429


async def test_the_coach_bills_the_caller_it_checks(app, new_client):
    """Finding 10: an admin asking the coach about a member's session is charged to the admin, not the member."""
    model = use_model(app)
    admin, _ = await org_with_admin(new_client)
    await seed_curated(app)
    member = new_client()
    await sign_in(member, "member", "member@example.org")
    await join(member, admin)
    session = await start_play(member, await card_id(member, "camp"))
    await say(member, session["id"], "Hello.")
    assert (await member.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await settle(app)
    admin_id = (await admin.get("/api/me")).json()["id"]
    events = await asyncio.wait_for(_ask(admin, session["id"]), timeout=10)
    assert any(event == "reply" for event, _ in events)
    assert model.calls["coach"] == 1
    rows = await _ledger_user_ids(app, session["id"], ("scope", "coach"))
    assert rows == {admin_id}  # the caller that was checked is the caller that is billed


async def test_parallel_coach_questions_admit_only_the_cap(app, new_client):
    """The per-session coach cap counts admissions, not ledger rows that do not exist yet."""
    model = use_model(app)
    limit(app, coach_questions_per_session=1)
    alice, _, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    await say(alice, session["id"], "Hello.")
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await settle(app)
    model.gates["scope"] = asyncio.Event()
    opener = asyncio.create_task(open_soon(model.gates["scope"]))  # the admitted question parks here
    results = await asyncio.gather(
        *[
            alice.post(f"/api/sessions/{session['id']}/coach", json={"question": "How did I do?", "history": []})
            for _ in range(3)
        ]
    )
    await opener
    await settle(app)
    assert sorted(response.status_code for response in results) == [200, 429, 429]
    assert model.calls["scope"] == 1


async def test_the_coach_cap_is_lifetime_per_session_not_per_day(app, new_client, monkeypatch):
    """The coach cap is per session: crossing midnight must not hand the player a fresh allowance."""
    model = use_model(app)
    limit(app, coach_questions_per_session=1)
    alice, _, scenario_id = await alice_with_scenario(app, new_client)
    session = await start_play(alice, scenario_id)
    await say(alice, session["id"], "Hello.")
    assert (await alice.post(f"/api/sessions/{session['id']}/end")).status_code == 200
    await settle(app)
    first = await _ask(alice, session["id"])
    assert any(event == "reply" for event, _ in first)

    from nlab.db import usage as usage_module

    real = usage_module.utcnow
    monkeypatch.setattr(usage_module, "utcnow", lambda: real() + timedelta(days=1))  # the admission clock moves
    calls = model.calls["scope"]
    refused = await alice.post(f"/api/sessions/{session['id']}/coach", json={"question": "Again?", "history": []})
    assert refused.status_code == 429  # still capped: the counter is for the session, not for the day
    assert model.calls["scope"] == calls  # refused before any provider call


async def test_parallel_guest_signups_use_only_the_quota(app, new_client):
    """Finding 17: one visitor cannot exhaust the shared signup quota with simultaneous requests."""
    limit(app, guest_play=True, guest_limit_signups_per_day=2)
    clients = [new_client() for _ in range(4)]
    results = await asyncio.gather(*[client.post("/api/auth/guest") for client in clients])
    assert sorted(response.status_code for response in results) == [204, 204, 429, 429]


def test_production_refuses_unpriced_or_invalid_model_prices():
    """A spending ceiling that cannot price a configured model must fail the production preflight."""
    from nlab.api.limits import validate_production
    from nlab.api.settings import Settings
    from nlab.llm import LLMConfig

    llm = LLMConfig(default=RoleConfig(model="chat", api_key=SecretStr("k")))
    production = dict(_env_file=None, secret_key="s", production=True, daily_spend_ceiling_usd=25.0)

    with pytest.raises(ValueError, match="price"):
        validate_production(Settings(**production, model_prices={}), llm, None)
    with pytest.raises(ValueError, match="price"):
        validate_production(Settings(**production, model_prices={"chat": (1.0, 1.0)}), llm, "painter")
    with pytest.raises(ValueError):
        validate_production(
            Settings(**production, model_prices={"chat": (-1.0, 1.0), "painter": (1.0, 1.0)}), llm, "painter"
        )
    with pytest.raises(ValueError):
        validate_production(
            Settings(**production, model_prices={"chat": (float("nan"), 1.0), "painter": (1.0, 1.0)}), llm, "painter"
        )
    validate_production(
        Settings(**production, model_prices={"chat": (1.0, 1.0), "painter": (1.0, 1.0)}), llm, "painter"
    )
    validate_production(  # the ceiling is off: no prices are required
        Settings(_env_file=None, secret_key="s", production=True, daily_spend_ceiling_usd=0.0, model_prices={}),
        llm,
        "painter",
    )


async def test_background_work_is_bounded():
    """Finding 12: background tasks have a concurrency cap and a bounded queue."""
    from nlab.api.background import Background

    background = Background(max_concurrent=1, max_pending=2)
    started, gate = asyncio.Event(), asyncio.Event()

    async def work() -> None:
        started.set()
        await gate.wait()

    background.spawn(work())
    await started.wait()  # one runs
    background.spawn(work())  # one queues
    assert background.spawn(work()) is False  # the queue is full
    gate.set()
    await background.drain(timeout=5)


async def _session_claim(app, session_id: str):
    from sqlalchemy import select as select_

    from nlab.db.models import PlaySession

    async with app.state.sessionmaker() as db:
        return await db.scalar(select_(PlaySession.turn_in_progress).where(PlaySession.id == uuid.UUID(session_id)))


async def _ask(client, session_id: str):
    from tests.api.support import ask_coach

    return await ask_coach(client, session_id, "How did I do?")


async def _ledger_user_ids(app, session_id: str, roles: tuple[str, ...]) -> set[str]:
    from nlab.db.models import LlmCall

    async with app.state.sessionmaker() as db:
        rows = await db.execute(
            select(LlmCall.user_id).where(LlmCall.session_id == uuid.UUID(session_id), LlmCall.role.in_(roles))
        )
    return {str(row) for (row,) in rows}
