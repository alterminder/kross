import pytest

from nlab.engine.conditions import (
    ALWAYS,
    NEVER,
    ConditionError,
    ProposalLine,
    matches,
    moves_in,
    parse_condition,
    without_goal,
)
from nlab.engine.state import State


def state(**dials: int) -> State:
    return State(scenario_id="test", dials=dials, level="technical")


def test_every_key_must_hold():
    condition = parse_condition({"trust_gte": 50, "hostility_lte": 40})
    assert matches(condition, state(trust=50, hostility=40))
    assert not matches(condition, state(trust=49, hostility=40))


def test_nested_any_and_all():
    condition = parse_condition(
        {"any": [{"move": "asks_good_question"}, {"all": [{"trust_gte": 60}, {"turn_gte": 2}]}]}
    )
    current = state(trust=70)
    assert matches(condition, current, moves={"asks_good_question"})
    assert not matches(condition, current)  # turn 0
    assert matches(condition, current.model_copy(update={"turn": 2}))


def test_a_missing_dial_never_passes_a_threshold():
    assert not matches(parse_condition({"anger_gte": 0}), state(trust=50))
    assert not matches(parse_condition({"anger_lte": 100}), state(trust=50))


def test_an_empty_condition_always_holds_and_no_condition_never_does():
    assert parse_condition({}) == ALWAYS and matches(ALWAYS, state())
    assert parse_condition(None) == NEVER and not matches(NEVER, state())


def test_proposal_reaches():
    condition = parse_condition(
        {"proposal_reaches": {"issue": "distribution", "side": "counterpart", "line": "bottom_line"}}
    )
    assert matches(condition, state(), proposals=[ProposalLine("distribution", "counterpart", "bottom_line")])
    assert not matches(condition, state(), proposals=[ProposalLine("distribution", "own", "bottom_line")])


def test_goal_requested_and_level():
    current = state().model_copy(update={"goal_requested": True, "level": "political"})
    assert matches(parse_condition({"goal_requested": True, "level": "political"}), current)
    assert not matches(parse_condition({"goal_requested": False}), current)


def test_without_goal_drops_only_the_goal_request():
    condition = parse_condition({"goal_requested": True, "trust_gte": 65})
    assert not matches(condition, state(trust=70))
    assert matches(without_goal(condition), state(trust=70))
    assert not matches(without_goal(condition), state(trust=60))
    nested = parse_condition({"any": [{"goal_requested": True}, {"trust_gte": 99}]})
    assert matches(without_goal(nested), state(trust=0))  # as in the hackathon engine: {} holds


@pytest.mark.parametrize(
    ("raw", "where"),
    [
        ({"trust_above": 5}, "trust_above"),
        ({"all": [{"move": "x"}, {"nope": 1}]}, "all.1.nope"),
        ({"any": {"move": "x"}}, "any"),
        ({"trust_gte": "high"}, "trust_gte"),
        ({"proposal_reaches": {"issue": "x"}}, "proposal_reaches"),
        ([{"move": "x"}], "condition"),
    ],
)
def test_a_bad_condition_names_the_key(raw, where):
    with pytest.raises(ConditionError, match=where):
        parse_condition(raw)


def test_moves_in_finds_every_move():
    condition = parse_condition({"any": [{"move": "a"}, {"all": [{"move": "b"}, {"trust_gte": 1}]}]})
    assert moves_in(condition) == {"a", "b"}


def test_describe_reads_as_a_sentence():
    from nlab.engine.conditions import describe

    assert describe(parse_condition({"trust_gte": 65})) == "trust at 65 or more"
    assert describe(parse_condition({"hostility_lte": 30})) == "hostility at 30 or less"
    assert describe(parse_condition({"move": "identifies_interest"})) == 'the "identifies interest" move'
    assert describe(parse_condition({"turn_gte": 4})) == "turn 4 or later"
    assert (
        describe(parse_condition({"any": [{"move": "asks_good_question"}, {"trust_gte": 45}]}))
        == 'the "asks good question" move or trust at 45 or more'
    )
    nested = parse_condition({"all": [{"trust_gte": 60}, {"any": [{"move": "a_b"}, {"move": "c_d"}]}]})
    assert describe(nested) == 'trust at 60 or more and (the "a b" move or the "c d" move)'
    assert describe(ALWAYS) == "from the start" and describe(NEVER) == "never"
