import copy

import pytest
from pydantic import ValidationError

from nlab.engine.models import Rules
from nlab.engine.state import Classification, Cue, Outcome, State
from tests.conftest import SCENARIO_IDS


def test_curated_scenarios_are_copied():
    assert SCENARIO_IDS == [
        "border_no_mans_land",
        "cacr_child_release_normative",
        "detention_police_station",
        "drill_bottomline_pause",
        "drill_deescalation",
        "drill_information_quality",
        "drill_level_shift",
        "drill_normative_pathway",
        "drill_redline_pressure",
        "fwb_guards_paid_in_kind",
        "hfa_staff_labour_dispute",
        "hfe_measles_campaign_levels",
        "imn_detainee_access_network",
        "negotiating_safe_access_education_child",
        "s01_idp_camp_access",
        "s08_tripartite_siege",
        "s09_hostile_checkpoint",
    ]


def test_rules_load_every_move_and_dial(rules):
    assert set(rules.state_variables) == {"trust", "rigidity", "hostility", "consistency"}
    assert rules.state_variables["consistency"].initial == 100
    assert len(rules.moves) == 73
    assert rules.moves["insults_counterpart"].ends_session is not None
    assert rules.consistency is not None and rules.consistency.recovery_per_turn == 5
    assert set(rules.hidden_interest_reveal_defaults) == {"tactical_reasoning", "motive_value"}


def test_rules_reject_a_threshold_on_an_unknown_dial(raw_rules):
    edited = copy.deepcopy(raw_rules)  # raw_rules is session-scoped; never mutate it
    edited["global_outcomes"][0]["when"] = {"consitency_lte": 0}  # the typo must not load silently
    with pytest.raises(ValidationError, match="consitency"):
        Rules.model_validate(edited)


def test_rubric_lists_its_dimensions(rubric):
    assert {"context_analysis", "questioning"} <= rubric.dimension_ids()


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_every_curated_scenario_loads(scenario, scenario_id):
    loaded = scenario(scenario_id)
    assert loaded.id == scenario_id
    assert loaded.counterpart.state_initial
    assert loaded.outcomes and loaded.red_lines


def test_scenario_fields_come_from_the_right_places(content, scenario):
    raw = content("s01_idp_camp_access")
    loaded = scenario("s01_idp_camp_access")
    assert loaded.counterpart.stated_position == raw["counterparts"][0]["iceberg"]["position"]["stated"]
    assert loaded.red_lines == [item["text"] for item in raw["trainee_brief"]["red_lines"]]
    assert loaded.must_refer == raw["trainee_brief"]["mandate"]["must_refer"]
    assert loaded.checklist == [item["id"] for item in raw["implementation_checklist"]]
    assert loaded.start_level == "technical"


def test_state_round_trips_through_json():
    state = State(scenario_id="x", dials={"trust": 40}, level="technical", cues=[Cue(kind="offer", label="Pass")])
    state.outcome = Outcome(id="passage", label="Pass", result="success", turn=3)
    assert State.model_validate_json(state.model_dump_json()) == state


def test_classification_accepts_null_quotes_and_extra_fields():
    parsed = Classification.model_validate(
        {
            "turn": 2,
            "moves": [{"id": "asks_good_question", "quote": None}],
            "red_lines": [{"text": "No payment", "quote": "pay", "action": "offers"}],
        }
    )
    assert parsed.moves[0].quote == ""
    assert parsed.red_lines[0].text == "No payment"
