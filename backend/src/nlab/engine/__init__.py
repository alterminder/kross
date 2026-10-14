"""Rules engine: pure functions over typed scenario, rules and state. No I/O.

Typical use: `Scenario.from_content(raw)` after `validate(raw, rules, rubric) == []`; `start(...)`, then per trainee
message `step(...)`, then `grant(...)` when the counterpart's reply grants the offer on the table.
"""

from nlab.engine.conditions import ConditionError
from nlab.engine.errors import EngineError
from nlab.engine.models import Rubric, Rules, Scenario
from nlab.engine.ops import (
    de_escalation_steps_completed,
    end,
    grant,
    grantable,
    inject,
    inject_text,
    is_red_line,
    nudge,
    set_dial,
    start,
    step,
    time_up,
)
from nlab.engine.rules import RuleOverrides, apply_changes, effective_rules, validate_overrides
from nlab.engine.state import Classification, Cue, Event, Offer, Outcome, State, Step
from nlab.engine.validate import Issue, validate

__all__ = [
    "Classification",
    "ConditionError",
    "Cue",
    "EngineError",
    "Event",
    "Issue",
    "Offer",
    "Outcome",
    "RuleOverrides",
    "Rubric",
    "Rules",
    "Scenario",
    "State",
    "Step",
    "apply_changes",
    "de_escalation_steps_completed",
    "effective_rules",
    "end",
    "grant",
    "grantable",
    "inject",
    "inject_text",
    "is_red_line",
    "nudge",
    "set_dial",
    "start",
    "step",
    "time_up",
    "validate",
    "validate_overrides",
]
