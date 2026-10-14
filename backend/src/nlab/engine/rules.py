"""An org's edits to the shipped behaviour rules: the dial changes each move causes."""

from __future__ import annotations

from collections.abc import Mapping

from nlab.engine.errors import EngineError
from nlab.engine.models import RuleOverrides, Rules

__all__ = [
    "Changes",
    "RuleOverrides",
    "Rules",
    "apply_changes",
    "effective_rules",
    "validate_overrides",
]

Changes = Mapping[str, Mapping[str, float]]


def validate_overrides(defaults: Rules, changes: Changes) -> list[str]:
    """Every problem in a requested edit: unknown move or dial, or a value outside -100..100."""
    problems = []
    for move_id, deltas in changes.items():
        if move_id not in defaults.moves:
            problems.append(f"Unknown move {move_id}")
            continue
        for dial, value in deltas.items():
            if dial not in defaults.state_variables:
                problems.append(f"{move_id}: unknown dial {dial}")
            elif not -100 <= value <= 100:
                problems.append(f"{move_id}.{dial}: {value} is outside -100..100")
    return problems


def apply_changes(defaults: Rules, current: RuleOverrides, changes: Changes) -> RuleOverrides:
    """The org's overrides after an edit. Values are rounded and zeros dropped; a move set back to its default is
    removed. Raises EngineError listing every problem, and then nothing is applied."""
    problems = validate_overrides(defaults, changes)
    if problems:
        raise EngineError("; ".join(problems))
    moves = dict(current.moves)
    for move_id, deltas in changes.items():
        clean = {dial: round(value) for dial, value in deltas.items() if round(value)}
        if clean == defaults.moves[move_id].deltas:
            moves.pop(move_id, None)
        else:
            moves[move_id] = clean
    return RuleOverrides(moves=moves)


def effective_rules(
    defaults: Rules,
    org_overrides: RuleOverrides | None = None,
    scenario_overrides: RuleOverrides | None = None,
) -> Rules:
    """The rules a session plays with: the defaults, with an org's whole-move edits applied first,
    and scenario overrides merged per dial afterward.
    """
    combined: dict[str, dict[str, int]] = {move_id: dict(spec.deltas) for move_id, spec in defaults.moves.items()}
    if org_overrides:
        for move_id, deltas in org_overrides.moves.items():
            if move_id in combined:
                combined[move_id] = dict(deltas)
    if scenario_overrides:
        for move_id, deltas in scenario_overrides.moves.items():
            if move_id in combined:
                combined[move_id].update(deltas)
            else:
                combined[move_id] = dict(deltas)
    moves = {
        move_id: spec.model_copy(update={"deltas": dict(combined[move_id])}) for move_id, spec in defaults.moves.items()
    }
    return defaults.model_copy(update={"moves": moves})
