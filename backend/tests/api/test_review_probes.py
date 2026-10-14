"""Regression tests from the PR #4 reviewer's probes (/tmp/pr4-review-probes.py). P7 and P9 asserted behaviour the
review changed (submit flow, curated scenarios stay public); their replacements live in test_scenarios.py."""

import asyncio
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import select, update

from nlab.db.models import LlmCall, Org, Role, RuleVersion, Scenario, ScenarioVersion, User, Visibility
from nlab.db.orgs import OrgContext
from nlab.db.rules import org_overrides, save_rule_edits
from nlab.llm import LLMConfig, RoleConfig
from tests.api.support import SUPERADMIN, count, draft, join, org_with_admin, seed_curated, sign_in
from tests.llm.fakes import FakeProvider

pytestmark = pytest.mark.anyio

CONFIG = LLMConfig(default=RoleConfig(model="m", api_key=SecretStr("k")))


async def _admin_context(app, org_id: str) -> OrgContext:
    async with app.state.sessionmaker() as db:
        user_id = await db.scalar(select(User.id).where(User.email.like("admin-%")))
    assert user_id is not None
    return OrgContext(user_id=user_id, org_id=uuid.UUID(org_id), role=Role.admin, is_personal=False)


async def test_P5_two_concurrent_rule_edits_both_survive(app, new_client):
    admin, _ = await org_with_admin(new_client)
    a, b = await asyncio.wait_for(
        asyncio.gather(
            admin.put("/api/rules", json={"moves": {"evades_direct_question": {"trust": -6}}}),
            admin.put("/api/rules", json={"moves": {"threatens": {"trust": -9}}}),
        ),
        timeout=10,  # a regression fails in 10 s instead of hanging
    )
    assert a.status_code == b.status_code == 200
    moves = {m["id"]: m for m in (await admin.get("/api/rules")).json()["moves"]}
    changed = sorted(k for k, m in moves.items() if m["changed"])
    assert changed == ["evades_direct_question", "threatens"], f"lost update: only {changed} kept"


async def test_P6_rule_saves_in_one_transaction_read_back_the_latest(app, new_client):
    admin, org_id = await org_with_admin(new_client)
    context = await _admin_context(app, org_id)
    async with app.state.sessionmaker() as db:
        rules = app.state.content.rules
        await save_rule_edits(db, context, rules, {"evades_direct_question": {"trust": -6}})
        await save_rule_edits(db, context, rules, {"evades_direct_question": {"trust": -7}})
        await save_rule_edits(db, context, rules, {"evades_direct_question": {"trust": -8}})
        latest = await org_overrides(db, context.org_id)
        numbers = sorted(await db.scalars(select(RuleVersion.number)))
    assert latest.moves == {"evades_direct_question": {"trust": -8}}, (latest.moves, numbers)
    assert numbers == [1, 2, 3]


async def test_P5b_interleaved_rule_edits_lose_neither(app, new_client):
    admin, org_id = await org_with_admin(new_client)
    context = await _admin_context(app, org_id)
    rules = app.state.content.rules
    async with app.state.sessionmaker() as a, app.state.sessionmaker() as b:
        await save_rule_edits(a, context, rules, {"evades_direct_question": {"trust": -6}})
        b_task = asyncio.create_task(save_rule_edits(b, context, rules, {"threatens": {"trust": -9}}))
        await asyncio.sleep(0.2)  # let b block on the org-row lock a holds
        await a.commit()
        await asyncio.wait_for(b_task, timeout=10)  # a regression fails in 10 s instead of hanging
        await b.commit()
    async with app.state.sessionmaker() as db:
        latest = await org_overrides(db, context.org_id)
    assert set(latest.moves) == {"evades_direct_question", "threatens"}, f"lost update: {latest.moves}"


async def test_P1_deleting_an_account_deletes_its_private_scenarios(app, new_client):
    """Spec: 'Deleting an account deletes the user's ... private scenarios.'"""
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    await client.post("/api/scenarios", json={"content": draft()})
    assert await count(app, Scenario) == 1
    assert (await client.delete("/api/me")).status_code == 204
    async with app.state.sessionmaker() as db:
        rows = (await db.execute(select(Scenario.visibility, Scenario.owner_id))).all()
    assert rows == [], f"private scenario survived account deletion: {rows}"


async def test_P1b_account_deletion_deletes_private_scenarios_in_shared_orgs(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    await bob.post("/api/scenarios", json={"content": draft()})
    assert (await bob.delete("/api/me")).status_code == 204
    async with app.state.sessionmaker() as db:
        rows = (await db.execute(select(Scenario.visibility, Scenario.owner_id))).all()
    versions = await count(app, ScenarioVersion)
    assert rows == [], f"private scenario survived account deletion: {rows}, {versions} version(s) kept"


async def test_P2_ledger_rows_survive_account_deletion(app, new_client):
    app.state.llm = (FakeProvider(["not json", "not json", "not json"]), CONFIG)
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    await client.post("/api/scenarios/convert", json={"text": "# A\n\nSome brief text for one scenario."})
    before = await count(app, LlmCall)
    assert before >= 1
    assert (await client.delete("/api/me")).status_code == 204
    assert await count(app, LlmCall) == before


async def test_P7_a_curated_scenario_cannot_be_unpublished(app, new_client):
    """Replaces the reviewer's P7: the review decided system-org scenarios stay public; delete them instead."""
    await seed_curated(app)
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    camp = next(c for c in (await root.get("/api/scenarios")).json() if c["cover"] == "camp")
    refused = await root.post(f"/api/scenarios/{camp['id']}/visibility", json={"visibility": "org"})
    assert refused.status_code == 409 and "cannot be unpublished" in refused.json()["detail"]
    assert (await seed_curated(app))["s01_idp_camp_access"] == "unchanged"
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert camp["id"] in {c["id"] for c in (await alice.get("/api/scenarios")).json()}


async def test_P12_deleting_a_curated_scenario_is_not_undone_by_the_next_seed(app, new_client):
    await seed_curated(app)
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    camp = next(c for c in (await root.get("/api/scenarios")).json() if c["cover"] == "camp")
    assert (await root.delete(f"/api/scenarios/{camp['id']}")).status_code == 204
    outcome = await seed_curated(app)
    assert outcome["s01_idp_camp_access"] == "retired", outcome


async def test_N4_publishing_moves_the_scenario_to_the_system_org(app, new_client):
    """A public scenario survives its author's account and source org going away."""
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    made = (await root.post("/api/scenarios", json={"content": draft("Curated by root")})).json()
    published = await root.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "public"})
    assert published.status_code == 204
    async with app.state.sessionmaker() as db:
        row = (
            await db.execute(
                select(Scenario.org_id, Org.is_system)
                .join(Org, Org.id == Scenario.org_id)
                .where(Scenario.id == uuid.UUID(made["id"]))
            )
        ).one()
    assert row[1], "published scenario did not move to the system org"
    assert (await root.delete("/api/me")).status_code == 204
    alice = new_client()
    await sign_in(alice, "alice", "alice@example.org")
    assert made["id"] in {c["id"] for c in (await alice.get("/api/scenarios")).json()}


async def test_the_seed_restores_a_curated_scenarios_visibility(app, new_client):
    """upsert_curated repairs a curated row whose visibility drifted from public."""
    await seed_curated(app)
    async with app.state.sessionmaker() as db:
        scenario = await db.scalar(select(Scenario).where(Scenario.slug == "s09_hostile_checkpoint"))
        scenario.visibility = Visibility.org  # simulate drift, e.g. a row touched by hand
        await db.commit()
    outcome = await seed_curated(app)
    assert outcome["s09_hostile_checkpoint"] == "updated"
    async with app.state.sessionmaker() as db:
        restored = await db.scalar(select(Scenario.visibility).where(Scenario.slug == "s09_hostile_checkpoint"))
    assert restored == Visibility.public


async def test_P4_two_concurrent_saves_one_wins_one_409_no_gap(app, new_client):
    client = new_client()
    await sign_in(client, "alice", "alice@example.org")
    scenario_id = (await client.post("/api/scenarios", json={"content": draft()})).json()["id"]
    results = await asyncio.wait_for(
        asyncio.gather(
            *[client.put(f"/api/scenarios/{scenario_id}", json={"content": draft(f"T{i}")}) for i in range(4)]
        ),
        timeout=10,  # a regression fails in 10 s instead of hanging
    )
    codes = sorted(r.status_code for r in results)
    async with app.state.sessionmaker() as db:
        numbers = sorted(await db.scalars(select(ScenarioVersion.number)))
        current = await db.scalar(select(Scenario.current_version))
    assert numbers == list(range(1, len(numbers) + 1)) and current == numbers[-1], (codes, numbers, current)
    assert set(codes) <= {200, 409}, codes


async def test_P8_a_member_cannot_delete_an_org_scenario_and_a_user_cannot_delete_a_curated_one(app, new_client):
    await seed_curated(app)
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)
    made = (await admin.post("/api/scenarios", json={"content": draft()})).json()
    await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})
    assert (await bob.delete(f"/api/scenarios/{made['id']}")).status_code == 403
    camp = next(c for c in (await bob.get("/api/scenarios")).json() if c["cover"] == "camp")
    assert (await bob.delete(f"/api/scenarios/{camp['id']}")).status_code == 403


async def test_P10_private_scenarios_stay_in_the_org_where_they_were_made(app, new_client):
    admin, _ = await org_with_admin(new_client)
    bob = new_client()
    await sign_in(bob, "bob", "bob@example.org")
    await join(bob, admin)  # bob's active org is now the admin's org
    made = (await bob.post("/api/scenarios", json={"content": draft()})).json()
    me = (await bob.get("/api/me")).json()
    personal = next(o for o in me["orgs"] if o["personal"])
    assert (await bob.post("/api/orgs/active", json={"org_id": personal["id"]})).status_code == 204
    assert (await bob.get(f"/api/scenarios/{made['id']}")).status_code == 404


async def test_M07_an_org_admin_cannot_pull_a_public_scenario_back_into_their_org(app, new_client):
    admin, _ = await org_with_admin(new_client)
    made = (await admin.post("/api/scenarios", json={"content": draft()})).json()
    async with app.state.sessionmaker() as db:  # a public row still in its source org (drift, pre-SF5 data)
        await db.execute(
            update(Scenario).where(Scenario.id == uuid.UUID(made["id"])).values(visibility=Visibility.public)
        )
        await db.commit()
    refused = await admin.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "org"})
    assert refused.status_code == 403


async def test_P11_a_system_org_is_created_once(app):
    await asyncio.wait_for(asyncio.gather(seed_curated(app), seed_curated(app)), timeout=10)
    async with app.state.sessionmaker() as db:
        orgs = list(await db.scalars(select(Org.id).where(Org.is_system.is_(True))))
        slugs = list(await db.scalars(select(Scenario.slug)))
    assert len(orgs) == 1 and len(slugs) == len(app.state.content.curated), (len(orgs), len(slugs))
