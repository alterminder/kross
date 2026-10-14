import uuid

import pytest
from sqlalchemy import select

from nlab.db.models import Scenario
from tests.api.support import SUPERADMIN, draft, seed_curated, sign_in, with_curated_title

pytestmark = pytest.mark.anyio


async def test_seeding_twice_changes_nothing_the_second_time(app):
    first = await seed_curated(app)
    assert len(first) == len(app.state.content.curated) and set(first.values()) == {"created"}
    assert set((await seed_curated(app)).values()) == {"unchanged"}


async def test_changed_curated_content_becomes_a_new_version(app, new_client):
    await seed_curated(app)
    outcome = await seed_curated(app, with_curated_title(app, "s09_hostile_checkpoint", " (revised)"))
    assert outcome["s09_hostile_checkpoint"] == "updated"
    assert [value for key, value in outcome.items() if key != "s09_hostile_checkpoint"] == ["unchanged"] * (
        len(app.state.content.curated) - 1
    )


async def test_a_content_change_adds_a_version_and_shows_it(app, new_client):
    """Mutants M13/M14: a changed curated file must add a version, never edit one in place or skip the change."""
    from nlab.db.models import ScenarioVersion
    from tests.api.support import SUPERADMIN, count, sign_in

    await seed_curated(app)
    outcome = await seed_curated(app, with_curated_title(app, "s09_hostile_checkpoint", " (revised)"))
    assert outcome["s09_hostile_checkpoint"] == "updated"
    assert await count(app, ScenarioVersion) == len(app.state.content.curated) + 1
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    card = next(c for c in (await root.get("/api/scenarios")).json() if c["title"].endswith("(revised)"))
    assert card["version"] == 2


async def test_R2_the_seed_creates_its_own_row_when_a_published_copy_shares_the_slug(app, new_client):
    """a superadmin publishes their own scenario whose id is a curated slug before the first seed.
    The seed must create the curated row, not version the superadmin's scenario."""
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    made = (await root.post("/api/scenarios", json={"content": draft("Root's take", "s09_hostile_checkpoint")})).json()
    assert (
        await root.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "public"})
    ).status_code == 204
    outcome = await seed_curated(app)
    assert outcome["s09_hostile_checkpoint"] == "created", outcome["s09_hostile_checkpoint"]
    async with app.state.sessionmaker() as db:
        mine = await db.scalar(select(Scenario.current_version).where(Scenario.id == uuid.UUID(made["id"])))
    assert mine == 1, "the seed wrote the curated file into root's published copy"


async def test_R2b_a_deleted_curated_scenario_stays_retired_next_to_a_published_copy(app, new_client):
    """with a published copy sharing the slug, deleting the curated row must make the seed report
    `retired`, never write into the copy."""
    await seed_curated(app)
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    made = (await root.post("/api/scenarios", json={"content": draft("Root's take", "s09_hostile_checkpoint")})).json()
    await root.post(f"/api/scenarios/{made['id']}/visibility", json={"visibility": "public"})
    cards = (await root.get("/api/scenarios")).json()
    curated = next(c for c in cards if c["cover"] == "checkpoint" and c["id"] != made["id"])
    assert (await root.delete(f"/api/scenarios/{curated['id']}")).status_code == 204
    outcome = await seed_curated(app)
    async with app.state.sessionmaker() as db:
        mine = await db.scalar(select(Scenario.current_version).where(Scenario.id == uuid.UUID(made["id"])))
    assert outcome["s09_hostile_checkpoint"] == "retired"
    assert mine == 1, "the seed wrote the curated file into root's published copy"


async def test_R9_a_curated_scenario_keeps_its_slug_over_an_api_rename(app, new_client):
    """a PUT that changes the content id must not change a curated scenario's slug (the files win,
    no duplicate appears on the next seed)."""
    await seed_curated(app)
    root = new_client()
    await sign_in(root, "root", SUPERADMIN)
    s09 = next(c for c in (await root.get("/api/scenarios")).json() if c["cover"] == "checkpoint")
    body = (await root.get(f"/api/scenarios/{s09['id']}")).json()["content"]
    body["id"] = "s09_renamed"
    assert (await root.put(f"/api/scenarios/{s09['id']}", json={"content": body})).status_code == 200
    outcome = await seed_curated(app)
    assert outcome["s09_hostile_checkpoint"] == "updated"  # the file's content wins as a new version
    public = [c for c in (await root.get("/api/scenarios")).json() if c["visibility"] == "public"]
    assert len(public) == len(app.state.content.curated), (outcome["s09_hostile_checkpoint"], len(public))
