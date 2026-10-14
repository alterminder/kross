"""inject_text: a free-text trainer twist, rewritten by the director and checked for bias."""

import pytest

from nlab.engine.errors import EngineError
from nlab.engine.ops import end, inject_text, set_dial, start, step
from tests.engine.support import QUIET


def test_inject_text_appends_a_trainer_record(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = start(sc, rules).state
    bias = {"flagged": True, "reason": "plays on an ethnic stereotype"}
    result = inject_text(state, "Make him furious, these people are hot-headed", "The counterpart grows furious", bias)
    assert state.injections == []  # inputs are never modified
    (record,) = result.state.injections
    assert record.id == "free_1"
    assert record.label == "Trainer twist"
    assert record.instruction == "The counterpart grows furious"
    assert record.source == "trainer"
    assert record.turn == result.state.turn
    assert record.original == "Make him furious, these people are hot-headed"
    assert record.rewritten == "The counterpart grows furious"
    assert record.bias == bias


def test_inject_text_reaches_the_counterpart_like_a_preset_twist(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = start(sc, rules).state
    state = inject_text(state, "A convoy is attacked nearby", "News arrives: a convoy was attacked", None).state
    # the counterpart's next prompt reads state.injections, recent turns only (llm.counterpart): the record sits
    # in the same list a preset twist's does, and survives the turn window like one
    assert [item.instruction for item in state.injections if item.turn >= state.turn - 1] == [
        "News arrives: a convoy was attacked"
    ]
    after = step(sc, rules, state, "Let us continue.", QUIET).state
    assert "News arrives: a convoy was attacked" in [
        item.instruction for item in after.injections if item.turn >= after.turn - 1
    ]


def test_inject_text_emits_one_event_and_ids_count_up(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = set_dial(start(sc, rules).state, "trust", 60).state
    first = inject_text(state, "one", "One rewritten", None)
    assert [(event.source, event.kind, event.ref) for event in first.events] == [("trainer", "injection", "free_1")]
    second = inject_text(first.state, "two", "Two rewritten", None).state
    assert [item.id for item in second.injections] == ["free_1", "free_2"]


def test_inject_text_after_the_end_raises_and_never_ends_the_session(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = start(sc, rules).state
    state = inject_text(state, "Panic", "Panic spreads", None).state
    assert state.outcome is None  # the trainer steers; the next trainee message decides
    ended = end(state).state
    with pytest.raises(EngineError):
        inject_text(ended, "too late", "Too late", None)
