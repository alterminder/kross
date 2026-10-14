"""The active org's behaviour rules: how much each move changes each dial. Everyone reads; admins edit."""

from fastapi import APIRouter, Request

from nlab.api.deps import AdminDep, Db, OrgDep, content_of
from nlab.api.schemas import MoveOut, RulesIn, RulesOut
from nlab.db.orgs import OrgContext
from nlab.db.rules import org_overrides, save_rule_edits
from nlab.engine import RuleOverrides, effective_rules

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _rules_out(request: Request, context: OrgContext, overrides: RuleOverrides) -> RulesOut:
    defaults = content_of(request).rules
    effective = effective_rules(defaults, overrides)
    return RulesOut(
        dials=list(defaults.state_variables),
        moves=[
            MoveOut(
                id=move_id,
                description=" ".join(spec.description.split()),
                source=spec.source,
                deltas=effective.moves[move_id].deltas,
                default=spec.deltas,
                changed=move_id in overrides.moves,
                ends_session=spec.ends_session is not None,
            )
            for move_id, spec in defaults.moves.items()
        ],
        can_edit=context.is_admin,
    )


@router.get("")
async def read_rules(context: OrgDep, request: Request, db: Db) -> RulesOut:
    return _rules_out(request, context, await org_overrides(db, context.org_id))


@router.put("")
async def edit_rules(body: RulesIn, context: AdminDep, request: Request, db: Db) -> RulesOut:
    overrides = await save_rule_edits(db, context, content_of(request).rules, body.moves)
    await db.commit()
    return _rules_out(request, context, overrides)
