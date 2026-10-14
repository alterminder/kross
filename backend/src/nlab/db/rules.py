"""An org's behaviour rules: the shipped defaults plus the org's saved edits of move dial changes."""

import copy
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nlab.db.models import Org, RuleVersion
from nlab.db.orgs import OrgContext
from nlab.engine import RuleOverrides, Rules, apply_changes


async def org_overrides(db: AsyncSession, org_id: uuid.UUID) -> RuleOverrides:
    """The org's latest saved edits, or none."""
    latest = await db.scalar(
        select(RuleVersion.overrides).where(RuleVersion.org_id == org_id).order_by(RuleVersion.number.desc()).limit(1)
    )
    return RuleOverrides.model_validate({"moves": latest or {}})


async def save_rule_edits(
    db: AsyncSession, context: OrgContext, defaults: Rules, changes: Mapping[str, Mapping[str, float]]
) -> RuleOverrides:
    """Applies an edit and stores the result as a new version. Raises EngineError (422) naming every problem.
    The org-row lock serialises concurrent saves so each one builds on the other's committed edits."""
    await db.execute(select(Org.id).where(Org.id == context.org_id).with_for_update(key_share=True))
    latest = await db.scalar(
        select(RuleVersion).where(RuleVersion.org_id == context.org_id).order_by(RuleVersion.number.desc()).limit(1)
    )
    current = RuleOverrides.model_validate({"moves": latest.overrides if latest else {}})
    updated = apply_changes(defaults, current, changes)
    db.add(
        RuleVersion(
            org_id=context.org_id,
            number=(latest.number if latest else 0) + 1,
            overrides=updated.moves,
            created_by=context.user_id,
        )
    )
    await db.flush()
    return updated


def pinned_rules(
    raw_defaults: dict[str, Any],
    org_overrides: RuleOverrides | None = None,
    scenario_overrides: RuleOverrides | None = None,
) -> dict[str, Any]:
    """The raw behaviour rules with an org's whole-move edits and scenario's per-dial edits applied:
    what a session stores at start and plays with.
    """
    pinned = copy.deepcopy(raw_defaults)
    moves = pinned.setdefault("moves", {})
    if org_overrides:
        for move_id, deltas in org_overrides.moves.items():
            if move_id in moves:
                moves[move_id]["deltas"] = dict(deltas)
    if scenario_overrides:
        for move_id, deltas in scenario_overrides.moves.items():
            move = moves.setdefault(move_id, {"deltas": {}})
            move.setdefault("deltas", {}).update(deltas)
    return pinned
