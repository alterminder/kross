import pytest

from nlab.engine.errors import EngineError
from nlab.engine.ops import start, step
from nlab.engine.rules import RuleOverrides, apply_changes, effective_rules, validate_overrides
from nlab.engine.state import Classification

SAY = Classification.model_validate({"moves": [{"id": "clarifies_operational_detail", "quote": "1 truck"}]})


def trust_after_one_turn(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    return step(sc, rules, start(sc, rules).state, "we have 1 truck", SAY).state.dials["trust"]


def test_an_edit_applies_is_stored_minimally_and_resets_to_the_default(scenario, rules):
    assert trust_after_one_turn(scenario, rules) == 37  # default +2

    edited = apply_changes(rules, RuleOverrides(), {"clarifies_operational_detail": {"trust": 5, "rigidity": -2}})
    assert edited.moves == {"clarifies_operational_detail": {"trust": 5, "rigidity": -2}}
    assert trust_after_one_turn(scenario, effective_rules(rules, edited)) == 40
    assert rules.moves["clarifies_operational_detail"].deltas == {"trust": 2}  # the defaults are never modified

    assert apply_changes(rules, edited, {"clarifies_operational_detail": {"trust": 2}}).moves == {}  # back to default


def test_values_are_rounded_and_zeros_dropped(rules):
    edited = apply_changes(rules, RuleOverrides(), {"threatens": {"trust": 2.6, "rigidity": 0.2}})
    assert edited.moves == {"threatens": {"trust": 3}}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"no_such_move": {"trust": 1}}, "Unknown move"),
        ({"threatens": {"anger": 1}}, "unknown dial"),
        ({"threatens": {"trust": 500}}, "outside"),
    ],
)
def test_a_bad_edit_is_rejected_and_changes_nothing(rules, changes, message):
    current = RuleOverrides(moves={"threatens": {"trust": -9}})
    with pytest.raises(EngineError, match=message):
        apply_changes(rules, current, changes)
    assert current.moves == {"threatens": {"trust": -9}}
    assert validate_overrides(rules, changes)


def test_the_penalty_move_exists(rules):
    assert rules.moves["evades_direct_question"].deltas == {"trust": -3}


def test_scenario_overrides_precedence_and_event_reason(scenario, rules):
    base_sc = scenario("s01_idp_camp_access")
    # Base: default delta +2 -> 37
    step_base = step(base_sc, rules, start(base_sc, rules).state, "we have 1 truck", SAY)
    assert step_base.state.dials["trust"] == 37
    assert not any(e.reason == "scenario override" for e in step_base.events if e.kind == "dial")

    org_ov = RuleOverrides(moves={"clarifies_operational_detail": {"trust": 5}})
    rules_org = effective_rules(rules, org_ov)
    step_org = step(base_sc, rules_org, start(base_sc, rules_org).state, "we have 1 truck", SAY)
    assert step_org.state.dials["trust"] == 40
    assert not any(e.reason == "scenario override" for e in step_org.events if e.kind == "dial")

    # Scenario with override
    sc_ov = RuleOverrides(moves={"clarifies_operational_detail": {"trust": 8}})
    sc_with_ov = base_sc.model_copy(update={"overrides": sc_ov})
    # Precedence: defaults -> org_ov -> sc_ov
    rules_combined = effective_rules(rules, org_ov, sc_ov)
    step_sc = step(sc_with_ov, rules_combined, start(sc_with_ov, rules_combined).state, "we have 1 truck", SAY)
    assert step_sc.state.dials["trust"] == 43
    dial_events = [
        e for e in step_sc.events if e.kind == "dial" and e.dial == "trust" and e.ref == "clarifies_operational_detail"
    ]
    assert dial_events
    assert dial_events[0].reason == "scenario override"


def test_overriding_single_dial_preserves_inherited_deltas(scenario, rules):
    base_sc = scenario("s01_idp_camp_access")
    default_deltas = rules.moves["argues_principles_only"].deltas
    assert "trust" in default_deltas and "rigidity" in default_deltas

    # Override trust only: rigidity must be preserved from defaults
    sc_ov = RuleOverrides(moves={"argues_principles_only": {"trust": -8}})
    eff = effective_rules(rules, None, sc_ov)
    assert eff.moves["argues_principles_only"].deltas["trust"] == -8
    assert eff.moves["argues_principles_only"].deltas["rigidity"] == default_deltas["rigidity"]

    sc_with_ov = base_sc.model_copy(update={"overrides": sc_ov})
    say = Classification.model_validate({"moves": [{"id": "argues_principles_only", "quote": "IHL dictates"}]})
    res = step(sc_with_ov, eff, start(sc_with_ov, eff).state, "IHL dictates", say)

    trust_events = [e for e in res.events if e.kind == "dial" and e.dial == "trust"]
    rigidity_events = [e for e in res.events if e.kind == "dial" and e.dial == "rigidity"]
    assert trust_events and trust_events[0].reason == "scenario override"
    assert rigidity_events and rigidity_events[0].reason == ""


def test_org_rules_can_disable_default_dial_effects(scenario, rules):
    base_sc = scenario("s01_idp_camp_access")
    assert rules.moves["evades_direct_question"].deltas == {"trust": -3}

    # Org sets penalty to 0: apply_changes drops zeros, storing an empty dict
    org_ov = apply_changes(rules, RuleOverrides(), {"evades_direct_question": {"trust": 0}})
    assert org_ov.moves == {"evades_direct_question": {}}

    eff = effective_rules(rules, org_ov)
    assert eff.moves["evades_direct_question"].deltas == {}

    evade = Classification.model_validate({"moves": [{"id": "evades_direct_question", "quote": "..."}]})
    res = step(base_sc, eff, start(base_sc, eff).state, "...", evade)
    # Trust stays at initial 35, does not drop to 32
    assert res.state.dials["trust"] == 35
