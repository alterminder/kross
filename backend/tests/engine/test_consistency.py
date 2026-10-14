import pytest

from nlab.engine.errors import EngineError
from nlab.engine.ops import set_dial, start, step
from nlab.engine.state import Classification

SCENARIOS = ["s01_idp_camp_access", "s09_hostile_checkpoint"]


def say(sc, rules, state, text, *moves):
    classification = Classification.model_validate({"moves": [{"id": move, "quote": text} for move in moves]})
    return step(sc, rules, state, text, classification).state


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_every_session_starts_consistent(scenario, rules, scenario_id):
    assert start(scenario(scenario_id), rules).state.dials["consistency"] == 100


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_repeated_nonsense_breaks_the_conversation(scenario, rules, scenario_id):
    sc = scenario(scenario_id)
    s = start(sc, rules).state
    trust = s.dials["trust"]
    s = say(sc, rules, s, "Bananas fly purple over the moon.", "nonsense")
    assert s.dials["consistency"] == 65 and s.dials["trust"] == trust - 5 and s.outcome is None
    assert any("Speak plainly" in cue.text for cue in s.cues)
    s = say(sc, rules, s, "My grandmother's bicycle is the mandate.", "nonsense")
    assert s.dials["consistency"] == 30 and s.outcome is None
    assert any("doubt the delegate is serious" in cue.text for cue in s.cues)
    s = say(sc, rules, s, "Blue cheese seven helicopter.", "nonsense")
    assert s.dials["consistency"] == 0
    assert s.outcome is not None and s.outcome.id == "conversation_broke_down" and s.outcome.result == "fail"


def test_breakdown_wins_over_a_scenario_success(scenario, rules):
    sc = scenario("s09_hostile_checkpoint")
    s = start(sc, rules).state
    for dial, value in (("trust", 90), ("rigidity", 10), ("hostility", 5), ("consistency", 20)):
        s = set_dial(s, dial, value).state
    s = say(sc, rules, s, "Blue cheese, can we pass?", "nonsense")
    assert s.outcome is not None and s.outcome.id == "conversation_broke_down"


def test_contradiction_costs_trust_and_coherent_turns_recover(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    s = start(sc, rules).state
    s = say(sc, rules, s, "Nobody saw anything this morning.", "story_contradiction")
    assert s.dials["trust"] == 35 - 12 and s.dials["consistency"] == 85
    s = say(sc, rules, s, "Let us talk about the route.")
    recovered = step(sc, rules, s, "Which checkpoints are open?", Classification())
    assert recovered.state.dials["consistency"] == 95
    assert any(event.reason == "coherent message: consistency recovers" for event in recovered.events)


def test_crude_language_is_a_small_penalty_not_a_fail(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    s = say(sc, rules, start(sc, rules).state, "Damn, this is a hard situation.", "crude_language")
    assert s.dials["consistency"] == 90 and s.outcome is None


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_insult_zeroes_consistency_and_ends_immediately(scenario, rules, scenario_id):
    sc = scenario(scenario_id)
    s = say(sc, rules, start(sc, rules).state, "You are a useless idiot.", "insults_counterpart")
    assert s.dials["consistency"] == 0
    assert s.outcome is not None and s.outcome.id == "insult" and s.outcome.result == "fail"
    assert s.flags[-1].id == "insult"
    with pytest.raises(EngineError, match="ended"):
        say(sc, rules, s, "Sorry.")


def test_a_state_without_the_consistency_dial_still_works(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    s = start(sc, rules).state
    del s.dials["consistency"]
    s = say(sc, rules, s, "Bananas.", "nonsense")
    assert "consistency" not in s.dials and s.outcome is None
