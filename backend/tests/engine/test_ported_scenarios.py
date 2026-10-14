import pytest

from nlab.engine.ops import grant, start, step
from nlab.engine.state import Classification
from nlab.engine.validate import validate

PORTED = ["detention_police_station", "border_no_mans_land"]
GOOD_TURNS = [
    ["shows_respect_curiosity", "proposes_shared_objective"],
    ["asks_good_question", "acknowledges_emotion"],
    ["identifies_interest", "unpacks_principle"],
    ["offers_options", "asks_good_question"],
    ["shows_respect_curiosity", "identifies_interest"],
    ["asks_good_question", "offers_options"],
    ["proposes_shared_objective", "acknowledges_emotion"],
]


def turn(sc, rules, state, moves, asked=False, red_line=None):
    text = "Message: " + " / ".join(moves) if moves else "Message."
    classification = Classification.model_validate(
        {
            "moves": [{"id": move, "quote": move} for move in moves],
            "asked_for_goal": asked,
            "red_lines": [{"text": red_line, "quote": "Message"}] if red_line else [],
        }
    )
    return step(sc, rules, state, text, classification).state


@pytest.mark.parametrize("scenario_id", PORTED)
def test_valid_and_opens_with_its_opening_line(content, scenario, rules, rubric, scenario_id):
    assert validate(content(scenario_id), rules, rubric) == []
    assert start(scenario(scenario_id), rules).opening == content(scenario_id)["counterparts"][0]["opening"]


@pytest.mark.parametrize("scenario_id", PORTED)
def test_good_negotiator_succeeds_and_unlocks_both_layers(scenario, rules, scenario_id):
    sc = scenario(scenario_id)
    state = start(sc, rules).state
    for moves in GOOD_TURNS:
        state = turn(sc, rules, state, moves)
        assert state.outcome is None  # never without asking
    state = turn(sc, rules, state, ["clarifies_operational_detail"], asked=True)
    assert state.outcome is None and state.offered is not None and state.offered.result == "success", state.dials
    state = grant(sc, state, "Agreed").state  # the counterpart's own yes
    assert state.outcome is not None and state.outcome.result == "success" and len(state.revealed) == 2


@pytest.mark.parametrize("scenario_id", PORTED)
def test_early_ask_gets_the_bottom_line(scenario, rules, scenario_id):
    sc = scenario(scenario_id)
    state = start(sc, rules).state
    for moves in GOOD_TURNS[:4]:
        state = turn(sc, rules, state, moves)
    state = turn(sc, rules, state, [], asked=True)
    assert state.outcome is None and state.offered is not None and state.offered.id == "bottom_line", state.dials
    granted = grant(sc, state, "Agreed").state
    assert granted.outcome is None and [item.id for item in granted.reached] == ["bottom_line"]


@pytest.mark.parametrize("scenario_id", PORTED)
def test_aggressive_negotiator_ends_the_meeting(scenario, rules, scenario_id):
    sc = scenario(scenario_id)
    state = start(sc, rules).state
    for _ in range(6):
        state = turn(sc, rules, state, ["aggressive_emotional_leverage"])
        if state.outcome:
            break
    assert state.outcome is not None and state.outcome.id == "meeting_ended"


@pytest.mark.parametrize("scenario_id", PORTED)
def test_bribe_crosses_the_payment_red_line(content, scenario, rules, scenario_id):
    sc = scenario(scenario_id)
    payment = next(
        line["text"] for line in content(scenario_id)["trainee_brief"]["red_lines"] if "payment" in line["text"].lower()
    )
    state = turn(sc, rules, start(sc, rules).state, [], red_line=payment)
    assert state.outcome is not None and state.outcome.id == "red_line"


@pytest.mark.parametrize("scenario_id", PORTED)
def test_time_runs_out(scenario, rules, scenario_id):
    sc = scenario(scenario_id)
    state = start(sc, rules).state
    for _ in range(20):
        state = turn(sc, rules, state, [])
    assert state.outcome is not None and state.outcome.id == "refused" and state.turn == 20


def test_detention_sunset_fires_at_turn_ten(scenario, rules):
    sc = scenario("detention_police_station")
    state = start(sc, rules).state
    for _ in range(10):
        state = turn(sc, rules, state, [])
    assert [item.id for item in state.injections] == ["sunset_warning"]
    assert state.injections[0].source == "auto"
