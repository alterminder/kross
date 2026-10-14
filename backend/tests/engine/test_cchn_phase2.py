from pydantic import SecretStr

from nlab.engine.models import Scenario
from nlab.engine.ops import de_escalation_steps_completed, start, step
from nlab.engine.state import Classification, MoveRecord, ProposalEvidence
from nlab.llm.answers import ClassifierAnswer
from nlab.llm.config import LLMConfig, RoleConfig
from nlab.llm.counterpart import counterpart_request
from nlab.llm.quotes import clean_classification


def test_classification_level_updates_state_and_emits_event(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    init_state = start(sc, rules).state
    assert init_state.level == "technical"

    classification = Classification(level="political")
    result = step(sc, rules, init_state, "Let us discuss policy.", classification)

    assert result.state.level == "political"
    assert any(e.source == "trainee" and e.kind == "level" and e.reason == "political" for e in result.events)

    # Same level again should update without re-emitting if level did not change
    result2 = step(sc, rules, result.state, "Still at political level.", Classification(level="political"))
    assert not any(e.kind == "level" and e.turn == result2.state.turn for e in result2.events)


def test_tier_sequencing_opens_with_tier3(content, rules):
    raw = content("s01_idp_camp_access")
    sc = Scenario.from_content(raw)
    assert sc.issue_tiers.get("escort") == 3

    init_state = start(sc, rules).state
    # Propose armed escort (Tier 3) on the first proposal
    msg = "We propose armed escort."
    classification = Classification(
        proposals=[ProposalEvidence(issue="escort", side="own", line="bottom_line", quote=msg)]
    )
    result = step(sc, rules, init_state, msg, classification)

    move_ids = [m.id for m in result.state.moves]
    assert "opens_with_tier3" in move_ids


def test_tier_sequencing_sequences_by_tier(content, rules):
    raw = content("s01_idp_camp_access")
    sc = Scenario.from_content(raw)
    assert sc.issue_tiers.get("operational_terms") == 1
    assert sc.issue_tiers.get("incident_responsibility") == 2
    assert sc.issue_tiers.get("escort") == 3

    init_state = start(sc, rules).state
    # Turn 1: Propose Convoy access (Tier 1)
    msg1 = "First, we clarify operational terms."
    res1 = step(
        sc,
        rules,
        init_state,
        msg1,
        Classification(
            proposals=[ProposalEvidence(issue="operational_terms", side="own", line="bottom_line", quote=msg1)]
        ),
    )
    assert "opens_with_tier3" not in [m.id for m in res1.state.moves]
    assert "sequences_by_tier" not in [m.id for m in res1.state.moves]

    # Turn 2: Propose incident responsibility (Tier 2)
    msg2 = "Next, we discuss incident responsibility."
    res2 = step(
        sc,
        rules,
        res1.state,
        msg2,
        Classification(
            proposals=[ProposalEvidence(issue="incident_responsibility", side="own", line="bottom_line", quote=msg2)]
        ),
    )
    assert "sequences_by_tier" not in [m.id for m in res2.state.moves]

    # Turn 3: Propose armed escort (Tier 3)
    msg3 = "Finally, we propose terms for the armed escort."
    res3 = step(
        sc,
        rules,
        res2.state,
        msg3,
        Classification(proposals=[ProposalEvidence(issue="escort", side="own", line="bottom_line", quote=msg3)]),
    )
    move_ids = [m.id for m in res3.state.moves]
    assert "sequences_by_tier" in move_ids


def test_de_escalation_steps_completed(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = start(sc, rules).state
    assert de_escalation_steps_completed(state) == []

    # Step 1: pause_and_acknowledge
    state.moves.append(MoveRecord(id="pause_and_acknowledge", turn=1, quote="I understand"))
    assert de_escalation_steps_completed(state) == [1]

    # Step 2: reformulates_with_check
    state.moves.append(MoveRecord(id="reformulates_with_check", turn=2, quote="so you mean"))
    assert de_escalation_steps_completed(state) == [1, 2]

    # Step 3: sets_emotion_aside
    state.moves.append(MoveRecord(id="sets_emotion_aside", turn=3, quote="let us set that aside"))
    assert de_escalation_steps_completed(state) == [1, 2, 3]

    # Remaining steps
    state.moves.append(MoveRecord(id="reframes_core_issue", turn=4, quote="reframe"))
    state.moves.append(MoveRecord(id="oco_questions", turn=5, quote="what would happen if"))
    state.moves.append(MoveRecord(id="offers_options", turn=6, quote="option A or B"))
    assert de_escalation_steps_completed(state) == [1, 2, 3, 4, 5, 6]


def test_counterpart_request_carries_level_and_preferred_level(content, scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = start(sc, rules).state
    state.level = "professional"

    raw = content("s01_idp_camp_access")
    cfg = LLMConfig(default=RoleConfig(model="test-model", api_key=SecretStr("k")))

    req = counterpart_request(cfg, raw, state, [])
    system_prompt = req.messages[0]["content"]
    assert '"level": "professional"' in system_prompt
    # Default fallback preferred_level is "technical"
    assert '"preferred_level": "technical"' in system_prompt

    # With custom preferred_level
    raw_custom = dict(raw)
    raw_custom["counterparts"] = [dict(raw["counterparts"][0], preferred_level="political")]
    req2 = counterpart_request(cfg, raw_custom, state, [])
    system_prompt2 = req2.messages[0]["content"]
    assert '"preferred_level": "political"' in system_prompt2


def test_clean_classification_preserves_valid_level():
    raw_valid = ClassifierAnswer.model_validate({"level": "political"})
    cleaned_valid, _ = clean_classification(raw_valid, "Hello", set())
    assert cleaned_valid.level == "political"

    # Invalid level string gets dropped by pydantic or clean_classification
    raw_none = ClassifierAnswer.model_validate({})
    cleaned_none, _ = clean_classification(raw_none, "Hello", set())
    assert cleaned_none.level is None
