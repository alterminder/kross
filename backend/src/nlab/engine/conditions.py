"""Condition trees used by outcomes, triggers, hidden-interest reveals and automatic injections.

In content a condition is a mapping whose keys must all hold. Keys: `all` and `any` (lists of conditions), `move`,
`goal_requested`, `level`, `proposal_reaches` (issue, side, line), `turn_gte`, `turn_lte`, `<dial>_gte`, `<dial>_lte`.
Unknown keys are errors; the hackathon engine silently treated them as false.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, assert_never

if TYPE_CHECKING:
    from nlab.engine.state import State


class ConditionError(ValueError):
    """A condition that cannot be parsed. The message starts with the path of the offending key."""


@dataclass(frozen=True)
class All:
    items: tuple[Condition, ...]


@dataclass(frozen=True)
class AnyOf:
    items: tuple[Condition, ...]


@dataclass(frozen=True)
class Move:
    id: str


@dataclass(frozen=True)
class GoalRequested:
    value: bool


@dataclass(frozen=True)
class Level:
    value: str


@dataclass(frozen=True)
class ProposalReaches:
    issue: str
    side: str
    line: str


@dataclass(frozen=True)
class Threshold:
    name: str  # "turn" or a dial
    op: Literal["gte", "lte"]
    value: float


@dataclass(frozen=True)
class Never:
    """No condition at all (for example a hidden interest without a reveal rule): never holds."""


type Condition = All | AnyOf | Move | GoalRequested | Level | ProposalReaches | Threshold | Never

ALWAYS: Condition = All(())
NEVER: Condition = Never()


@dataclass(frozen=True)
class ProposalLine:
    """An issue line the trainee's message reached this turn."""

    issue: str
    side: str
    line: str


def parse_condition(raw: Any, path: str = "") -> Condition:
    """Parse content into a condition tree. `None` means no condition (never holds); `{}` always holds."""
    if raw is None:
        return NEVER
    if not isinstance(raw, dict):
        raise ConditionError(f"{path or 'condition'}: expected a mapping, got {type(raw).__name__}")
    parts = [_parse_key(str(key), value, f"{path}.{key}" if path else str(key)) for key, value in raw.items()]
    return parts[0] if len(parts) == 1 else All(tuple(parts))


def _parse_key(key: str, value: Any, where: str) -> Condition:
    if key in ("all", "any"):
        if not isinstance(value, list):
            raise ConditionError(f"{where}: expected a list")
        items = tuple(parse_condition(item, f"{where}.{index}") for index, item in enumerate(value))
        return All(items) if key == "all" else AnyOf(items)
    if key == "move":
        return Move(_expect(value, str, where))
    if key == "goal_requested":
        return GoalRequested(_expect(value, bool, where))
    if key == "level":
        return Level(_expect(value, str, where))
    if key == "proposal_reaches":
        if not isinstance(value, dict) or set(value) != {"issue", "side", "line"}:
            raise ConditionError(f"{where}: expected issue, side and line")
        return ProposalReaches(str(value["issue"]), str(value["side"]), str(value["line"]))
    for suffix in ("_gte", "_lte"):
        if key.endswith(suffix) and len(key) > len(suffix):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ConditionError(f"{where}: expected a number")
            return Threshold(key.removesuffix(suffix), "gte" if suffix == "_gte" else "lte", value)
    raise ConditionError(f"{where}: unknown condition key")


def _expect[T](value: Any, kind: type[T], where: str) -> T:
    if not isinstance(value, kind):
        raise ConditionError(f"{where}: expected {kind.__name__}")
    return value


def matches(
    condition: Condition,
    state: State,
    moves: Collection[str] = (),
    proposals: Collection[ProposalLine] = (),
) -> bool:
    """Does the condition hold? `moves` and `proposals` are what the current trainee turn did; outside a turn both are
    empty, so `move` and `proposal_reaches` never hold there."""
    match condition:
        case All(items):
            return all(matches(item, state, moves, proposals) for item in items)
        case AnyOf(items):
            return any(matches(item, state, moves, proposals) for item in items)
        case Move(move_id):
            return move_id in moves
        case GoalRequested(value):
            return state.goal_requested is value
        case Level(value):
            return state.level == value
        case ProposalReaches(issue, side, line):
            return ProposalLine(issue, side, line) in proposals
        case Threshold(name, op, value):
            # a dial the state does not have never passes
            current = state.turn if name == "turn" else state.dials.get(name, -1 if op == "gte" else 101)
            return current >= value if op == "gte" else current <= value
        case Never():
            return False
        case _:
            assert_never(condition)


def describe(condition: Condition, *, nested: bool = False) -> str:
    """The condition as one plain sentence fragment, for a reader who is not editing it (for example the debrief's
    "what would have unlocked this"). `nested` wraps an "or" list in brackets when it sits inside another list."""
    match condition:
        case All(items):
            if not items:
                return "from the start"
            return " and ".join(describe(item, nested=len(items) > 1) for item in items)
        case AnyOf(items):
            text = " or ".join(describe(item, nested=True) for item in items) if items else "never"
            return f"({text})" if nested and len(items) > 1 else text
        case Move(move_id):
            return f'the "{move_id.replace("_", " ")}" move'
        case GoalRequested(value):
            return "you asked for the goal" if value else "you had not yet asked for the goal"
        case Level(value):
            return f'the conversation at "{value}" level'
        case ProposalReaches(issue, side, line):
            return f"a proposal reaching {issue.replace('_', ' ')} / {side} / {line.replace('_', ' ')}"
        case Threshold(name, op, value):
            number = f"{value:g}"
            if name == "turn":
                return f"turn {number} or later" if op == "gte" else f"by turn {number}"
            return f"{name} at {number} or more" if op == "gte" else f"{name} at {number} or less"
        case Never():
            return "never"
        case _:
            assert_never(condition)


def without_goal(condition: Condition) -> Condition:
    """The condition minus its goal-request tests: are the numbers already in range? (Asking is not agreeing.)"""
    match condition:
        case GoalRequested():
            return ALWAYS
        case All(items):
            return All(tuple(without_goal(item) for item in items))
        case AnyOf(items):
            return AnyOf(tuple(without_goal(item) for item in items))
        case _:
            return condition


def moves_in(condition: Condition) -> set[str]:
    """Every move id the condition refers to, at any depth."""
    match condition:
        case Move(move_id):
            return {move_id}
        case All(items) | AnyOf(items):
            return set().union(*(moves_in(item) for item in items))
        case _:
            return set()


def thresholds_in(condition: Condition) -> set[str]:
    """Every threshold name the condition refers to, at any depth: "turn" or a dial."""
    match condition:
        case Threshold(name):
            return {name}
        case All(items) | AnyOf(items):
            return set().union(*(thresholds_in(item) for item in items))
        case _:
            return set()
