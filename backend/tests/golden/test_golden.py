"""The new engine matches the hackathon engine on the action sequences of recorded sessions. One deliberate
difference: `threatens` and `aggressive_emotional_leverage` now raise the rubric's escalation flag (CCHN Tool 8), so
those entries were added to the recorded flags; everything else is replayed exactly."""

import json
from pathlib import Path
from typing import Any

import pytest

from nlab.engine import Classification, Scenario, State, end, grant, inject, set_dial, start, step

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.json"))


def project(state: State) -> dict[str, Any]:
    """The new state in the same shape as extract_golden.project."""
    return {
        "turn": state.turn,
        "dials": state.dials,
        "level": state.level,
        "goal_requested": state.goal_requested,
        "revealed": state.revealed,
        "covered_details": state.covered_details,
        "moves": [{"turn": m.turn, "id": m.id, "quote": m.quote} for m in state.moves],
        "flags": [{"turn": f.turn, "id": f.id, "quote": f.quote, "text": f.text} for f in state.flags],
        "proposals": [
            {"turn": p.turn, "issue": p.issue, "side": p.side, "line": p.line, "quote": p.quote}
            for p in state.proposals
        ],
        "injections": [
            {"id": i.id, "label": i.label, "instruction": i.instruction, "source": i.source, "turn": i.turn}
            for i in state.injections
        ],
        "cues": [c.model_dump() for c in state.cues],
        "offered": {"id": state.offered.id, "turn": state.offered.turn} if state.offered else None,
        "reached": [{"id": r.id, "label": r.label, "turn": r.turn} for r in state.reached],
        "outcome": {
            "id": state.outcome.id,
            "label": state.outcome.label,
            "result": state.outcome.result,
            "turn": state.outcome.turn,
        }
        if state.outcome
        else None,
    }


def test_there_are_fixtures():
    assert len(FIXTURES) >= 20


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_replay_matches_the_hackathon_engine(path, rules):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    sc = Scenario.from_content(fixture["scenario"])
    state = start(sc, rules).state
    for index, (action, expected) in enumerate(zip(fixture["actions"], fixture["expected"], strict=True)):
        match action["op"]:
            case "step":
                state = step(
                    sc, rules, state, action["text"], Classification.model_validate(action["classification"])
                ).state
            case "set_dial":
                state = set_dial(state, action["dial"], action["value"]).state
            case "inject":
                state = inject(sc, state, action["id"]).state
            case "grant":
                state = grant(sc, state, action["quote"]).state
            case "end":
                state = end(state).state
        assert project(state) == expected, f"action {index}: {action['op']}"
