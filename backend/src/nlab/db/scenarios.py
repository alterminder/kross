"""The scenario library. Every read goes through `visible_to`, the one place that decides who sees what: curated
(public) scenarios for everyone, org scenarios for the active org, private ones for their owner."""

import copy
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.auth_sessions import utcnow
from nlab.db.errors import Conflict, Forbidden, NotFound
from nlab.db.models import Org, Scenario, ScenarioVersion, Visibility
from nlab.db.orgs import OrgContext, ensure_system_org


@dataclass(frozen=True)
class Viewer:
    """Who is looking at the library: the active org context and the platform role."""

    context: OrgContext
    is_superadmin: bool


@dataclass(frozen=True)
class Entry:
    scenario: Scenario
    version: ScenarioVersion  # the current one


def visible_to(viewer: Viewer) -> ColumnElement[bool]:
    context = viewer.context
    clauses: list[ColumnElement[bool]] = [
        Scenario.visibility == Visibility.public,
        and_(Scenario.org_id == context.org_id, Scenario.visibility == Visibility.org),
        and_(
            Scenario.org_id == context.org_id,
            Scenario.visibility == Visibility.private,
            Scenario.owner_id == context.user_id,
        ),
    ]
    if context.is_admin:  # a member's submitted draft is visible to the org's admins, for publishing or returning
        clauses.append(
            and_(
                Scenario.org_id == context.org_id,
                Scenario.visibility == Visibility.private,
                Scenario.submitted_at.isnot(None),
            )
        )
    return and_(Scenario.deleted_at.is_(None), or_(*clauses))


def can_edit(scenario: Scenario, viewer: Viewer) -> bool:
    context = viewer.context
    if scenario.visibility == Visibility.public:
        return viewer.is_superadmin
    if scenario.org_id != context.org_id:
        return False
    if scenario.visibility == Visibility.org:
        return context.is_admin
    return scenario.owner_id == context.user_id


def can_review(scenario: Scenario, viewer: Viewer) -> bool:
    """An admin may read a submitted draft of their active org before deciding: publish it or return it."""
    context = viewer.context
    return (
        scenario.visibility == Visibility.private
        and scenario.submitted_at is not None
        and scenario.org_id == context.org_id
        and context.is_admin
    )


def _with_current() -> Select[Scenario, ScenarioVersion]:
    return select(Scenario, ScenarioVersion).join(
        ScenarioVersion,
        and_(ScenarioVersion.scenario_id == Scenario.id, ScenarioVersion.number == Scenario.current_version),
    )


def _summary(content: dict[str, Any]) -> tuple[str, str]:
    return str(content["id"])[:80], str(content.get("title") or content["id"])[:300]


async def list_scenarios(db: AsyncSession, viewer: Viewer) -> list[Entry]:
    """Public first, then the org's, then the viewer's private ones; by title within each."""
    rows = await db.execute(
        _with_current().where(visible_to(viewer)).order_by(Scenario.visibility.desc(), Scenario.title)
    )
    return [Entry(scenario, version) for scenario, version in rows]


async def get_entry(db: AsyncSession, viewer: Viewer, scenario_id: uuid.UUID) -> Entry:
    row = (await db.execute(_with_current().where(Scenario.id == scenario_id, visible_to(viewer)))).first()
    if row is None:
        raise NotFound("No such scenario")
    scenario, version = row
    return Entry(scenario, version)


async def visible_slugs(db: AsyncSession, viewer: Viewer) -> set[str]:
    return set(await db.scalars(select(Scenario.slug).where(visible_to(viewer))))


async def create_scenario(db: AsyncSession, viewer: Viewer, content: dict[str, Any], cover: str) -> Entry:
    """A private scenario of the viewer's, in their active org. The caller has validated the content."""
    context = viewer.context
    slug, title = _summary(content)
    scenario = Scenario(
        org_id=context.org_id,
        owner_id=context.user_id,
        visibility=Visibility.private,
        slug=slug,
        title=title,
        cover=cover,
        current_version=1,
    )
    db.add(scenario)
    await db.flush()
    version = ScenarioVersion(scenario_id=scenario.id, number=1, content=content, created_by=context.user_id)
    db.add(version)
    await db.flush()
    return Entry(scenario, version)


def copy_of(content: dict[str, Any], taken: set[str]) -> dict[str, Any]:
    """The content of a duplicate: the same scenario under a new id (`<id>_copy`, `_copy2`... not in `taken`) and a
    title that says it is a copy. The slug is capped at 80 characters, so a long id is cut before the suffix."""
    base = str(content["id"]).removesuffix("_copy")[:60] or "scenario"
    slug, number = f"{base}_copy", 1
    while slug in taken:
        number += 1
        slug = f"{base}_copy{number}"
    title = str(content.get("title") or content["id"])
    return {**copy.deepcopy(content), "id": slug, "title": f"{title} (copy)"}


async def update_scenario(
    db: AsyncSession, viewer: Viewer, scenario_id: uuid.UUID, content: dict[str, Any], cover: str | None
) -> Entry:
    """A new version. Two saves at once collide on (scenario_id, number): one of them gets 409."""
    scenario = (await get_entry(db, viewer, scenario_id)).scenario
    if not can_edit(scenario, viewer):
        raise Forbidden("You cannot edit this scenario")
    scenario.current_version += 1
    slug, title = _summary(content)
    scenario.title = title
    if not scenario.curated:  # a curated scenario's slug is its file's id; renaming it would duplicate it on reseed
        scenario.slug = slug
    if cover is not None:
        scenario.cover = cover
    version = ScenarioVersion(
        scenario_id=scenario.id, number=scenario.current_version, content=content, created_by=viewer.context.user_id
    )
    db.add(version)
    await db.flush()
    return Entry(scenario, version)


async def set_visibility(db: AsyncSession, viewer: Viewer, scenario_id: uuid.UUID, visibility: Visibility) -> None:
    scenario = (await get_entry(db, viewer, scenario_id)).scenario
    context = viewer.context
    system_id = await db.scalar(select(Org.id).where(Org.is_system.is_(True)))
    if Visibility.public in (visibility, scenario.visibility):
        if not viewer.is_superadmin:
            raise Forbidden("Only a platform superadmin can publish or unpublish curated scenarios")
    elif scenario.org_id != context.org_id or not context.is_admin:
        raise Forbidden("Only an admin of this org can change who sees a scenario")
    if scenario.org_id == system_id and visibility != Visibility.public:
        raise Conflict("Curated scenarios cannot be unpublished; delete it instead")
    if visibility == Visibility.private and scenario.owner_id is None:
        raise Conflict("This scenario has no author any more; delete it instead")
    scenario.visibility = visibility
    scenario.submitted_at = None  # every visibility change ends the review, publish or not
    if visibility == Visibility.public:
        # public means the system org: a public scenario no longer depends on its source org's lifetime
        scenario.org_id = (await ensure_system_org(db)).id


async def submit_scenario(db: AsyncSession, viewer: Viewer, scenario_id: uuid.UUID) -> None:
    """The owner asks the org's admins to publish their private scenario: it becomes visible to them."""
    scenario = (await get_entry(db, viewer, scenario_id)).scenario
    context = viewer.context
    if context.is_personal:
        raise Conflict("Your personal space has no org library; switch to a shared org first")
    if scenario.visibility != Visibility.private or scenario.owner_id != context.user_id:
        raise Forbidden("Only the author can submit a private scenario")
    scenario.submitted_at = utcnow()


async def return_scenario(db: AsyncSession, viewer: Viewer, scenario_id: uuid.UUID) -> None:
    """An admin hands a submitted draft back to its author: it stays private and leaves the admins' queue."""
    scenario = (await get_entry(db, viewer, scenario_id)).scenario
    context = viewer.context
    if scenario.org_id != context.org_id or not context.is_admin:
        raise Forbidden("Only an admin of this org can return a scenario")
    if scenario.visibility != Visibility.private or scenario.submitted_at is None:
        raise Conflict("Only a submitted draft can be returned")
    scenario.submitted_at = None


async def delete_scenario(db: AsyncSession, viewer: Viewer, scenario_id: uuid.UUID) -> None:
    """Hidden from everyone; the versions stay, because sessions pin them."""
    scenario = (await get_entry(db, viewer, scenario_id)).scenario
    if not can_edit(scenario, viewer):
        raise Forbidden("You cannot delete this scenario")
    scenario.deleted_at = utcnow()


async def upsert_curated(db: AsyncSession, org_id: uuid.UUID, content: dict[str, Any], cover: str) -> str:
    """Loads one curated scenario into the system org: "created", "updated" (a new version, or a cover or
    visibility restored), "retired" (its row was deleted; the seed leaves it deleted) or "unchanged"."""
    slug, title = _summary(content)
    scenario = await db.scalar(
        select(Scenario)
        .where(Scenario.org_id == org_id, Scenario.slug == slug, Scenario.curated.is_(True))
        .order_by(Scenario.deleted_at.isnot(None))  # live rows first: a published user copy never wins this lookup
    )
    if scenario is not None and scenario.deleted_at is not None:
        return "retired"
    if scenario is None:
        scenario = Scenario(
            org_id=org_id,
            owner_id=None,
            visibility=Visibility.public,
            curated=True,  # the one place a scenario becomes curated
            slug=slug,
            title=title,
            cover=cover,
            current_version=1,
        )
        db.add(scenario)
        await db.flush()
        db.add(ScenarioVersion(scenario_id=scenario.id, number=1, content=content, created_by=None))
        await db.flush()
        return "created"
    current = await db.scalar(
        select(ScenarioVersion.content).where(
            ScenarioVersion.scenario_id == scenario.id, ScenarioVersion.number == scenario.current_version
        )
    )
    changed = False
    if current != content:
        scenario.current_version += 1
        scenario.title = title
        db.add(
            ScenarioVersion(scenario_id=scenario.id, number=scenario.current_version, content=content, created_by=None)
        )
        changed = True
    if scenario.cover != cover:
        scenario.cover = cover
        changed = True
    if scenario.visibility != Visibility.public:  # curated means public; restore it if someone moved the row
        scenario.visibility = Visibility.public
        changed = True
    if not changed:
        return "unchanged"
    await db.flush()
    return "updated"
