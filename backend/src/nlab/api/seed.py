"""Loads the curated scenarios into the system org as public scenarios. Safe to repeat:
`uv run --env-file .env python -m nlab.api.seed`."""

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.api.content import CURATED_COVERS, Content, Cover, load_content
from nlab.api.settings import Settings
from nlab.db.engine import make_engine, make_sessionmaker
from nlab.db.orgs import ensure_system_org
from nlab.db.scenarios import upsert_curated
from nlab.engine import validate

SEED_LOCK = 720_301  # pg_advisory_xact_lock key: two seeds at once serialise instead of racing the lookups


async def seed_database(db: AsyncSession, content: Content) -> dict[str, str]:
    """{scenario id: "created" | "updated" | "unchanged"}. Refuses to load anything if a curated scenario is
    invalid."""
    await db.execute(select(func.pg_advisory_xact_lock(SEED_LOCK)))
    for scenario in content.curated:
        issues = validate(scenario, content.rules, content.rubric)
        if issues:
            raise ValueError(f"Curated scenario {scenario.get('id')} is invalid: {issues[0]}")
    org = await ensure_system_org(db)
    return {
        scenario["id"]: await upsert_curated(
            db, org.id, scenario, CURATED_COVERS.get(scenario["id"], Cover.field).value
        )
        for scenario in content.curated
    }


async def seed(settings: Settings) -> dict[str, str]:
    engine = make_engine(settings.resolved_database_url())
    try:
        async with make_sessionmaker(engine)() as db:
            outcome = await seed_database(db, load_content(settings.content_dir))
            await db.commit()
            return outcome
    finally:
        await engine.dispose()


def main() -> None:
    for scenario_id, outcome in asyncio.run(seed(Settings())).items():
        print(f"{outcome:9} {scenario_id}")


if __name__ == "__main__":
    main()
