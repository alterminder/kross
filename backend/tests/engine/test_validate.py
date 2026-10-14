import pytest

from nlab.engine.validate import validate
from tests.conftest import SCENARIO_IDS


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_curated_scenarios_are_valid(content, rules, rubric, scenario_id):
    assert validate(content(scenario_id), rules, rubric) == []


def test_a_schema_error_points_at_the_field(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["id"] = 5
    issues = validate(raw, rules, rubric)
    assert [issue.path for issue in issues] == ["id"]


def test_not_a_mapping(rules, rubric):
    assert validate(["nope"], rules, rubric)


def test_an_unknown_condition_key_is_reported(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["outcomes"][0]["when"] = {"trust_above": 50}
    issues = validate(raw, rules, rubric)
    assert any(issue.path.startswith("outcomes.0.when") and "trust_above" in issue.message for issue in issues)


def test_an_unknown_move_is_reported_at_any_depth(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["triggers"][0]["when"] = {"any": [{"move": "no_such_move"}, {"trust_gte": 10}]}
    issues = validate(raw, rules, rubric)
    assert any(issue.path.startswith("triggers.0") and "no_such_move" in issue.message for issue in issues)


def test_an_injection_with_an_unknown_dial_is_reported(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["injections"][0]["dials"] = {"anger": 5}
    assert any("anger" in issue.message for issue in validate(raw, rules, rubric))


def test_a_scenario_threshold_on_an_unknown_dial_is_reported(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["outcomes"][0]["when"] = {"anger_gte": 50}
    issues = validate(raw, rules, rubric)
    assert any(issue.path.startswith("outcomes.0.when") and "anger" in issue.message for issue in issues)


def test_an_injection_with_a_fractional_delta_is_reported(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["injections"][0]["dials"] = {"trust": 0.5}
    issues = validate(raw, rules, rubric)
    assert any(issue.path.startswith("injections.0.dials") for issue in issues)


def test_an_unknown_rubric_dimension_is_reported(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["rubric"]["dimensions"].append("charisma")
    assert any("charisma" in issue.message for issue in validate(raw, rules, rubric))


def test_an_outcome_without_a_condition_is_reported(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["outcomes"][0]["when"] = {}
    assert any(issue.path.startswith("outcomes.0.when") for issue in validate(raw, rules, rubric))


def test_valid_scenario_overrides_produce_no_issues(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["overrides"] = {"moves": {"argues_principles_only": {"deltas": {"trust": -8, "rigidity": 8}}}}
    assert validate(raw, rules, rubric) == []


def test_invalid_scenario_overrides_are_reported(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["overrides"] = {
        "moves": {
            "no_such_move": {"deltas": {"trust": -5}},
            "argues_principles_only": {
                "deltas": {
                    "unknown_dial": 2,
                    "trust": 500,
                    "turn": 5,
                }
            },
        }
    }
    issues = validate(raw, rules, rubric)
    paths = {issue.path for issue in issues}
    assert "overrides.moves.no_such_move" in paths
    assert "overrides.moves.argues_principles_only.deltas.unknown_dial" in paths
    assert "overrides.moves.argues_principles_only.deltas.trust" in paths
    assert "overrides.moves.argues_principles_only.deltas.turn" in paths


def test_overrides_mapping_structure_validation(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["overrides"] = ["not", "a", "dict"]
    issues = validate(raw, rules, rubric)
    assert any(i.path == "overrides" for i in issues)

    raw["overrides"] = {"moves": ["not", "a", "dict"]}
    issues = validate(raw, rules, rubric)
    assert any(i.path == "overrides.moves" and "expected a mapping of moves" in i.message for i in issues)

    raw["overrides"] = {"moves": {"argues_principles_only": ["not", "a", "dict"]}}
    issues = validate(raw, rules, rubric)
    assert any(i.path == "overrides.moves.argues_principles_only" and "dial deltas" in i.message for i in issues)


def test_a_fallback_line_is_a_non_empty_string(content, rules, rubric):
    data = content("s01_idp_camp_access")
    data["counterparts"][0]["fallback"] = "Give me a moment."
    assert validate(data, rules, rubric) == []
    data["counterparts"][0]["fallback"] = ""
    assert [issue.path for issue in validate(data, rules, rubric)] == ["counterparts.0.fallback"]


def phases(*specs):
    return [
        {"id": id, "instruction": f"Act as {id}.", **({"until_turn": until} if until else {})} for id, until in specs
    ]


def test_timing_is_optional_and_a_good_one_validates(content, rules, rubric):
    data = content("s01_idp_camp_access")
    data["timing"] = {
        "phases": phases(("greeting", 1), ("bargaining", 6), ("wrap_up", None)),
        "warnings": [3, 1],
        "on_timeout": "fail",
    }
    assert validate(data, rules, rubric) == []


def test_the_stages_must_be_ordered_and_the_last_runs_to_the_end(content, rules, rubric):
    data = content("s01_idp_camp_access")
    cases = {
        (("a", 5), ("b", 3), ("c", None)): "timing.phases.1.until_turn",  # not rising
        (("a", 3), ("b", None), ("c", None)): "timing.phases.1.until_turn",  # a middle stage without an end
        (("a", 3), ("b", 6)): "timing.phases.1.until_turn",  # the last stage with one
        (("a", 3), ("a", None)): "timing.phases.1.id",  # a stage twice
    }
    for specs, path in cases.items():
        data["timing"] = {"phases": phases(*specs)}
        assert path in [issue.path for issue in validate(data, rules, rubric)], specs


def test_timing_rejects_unknown_keys_and_bad_values(content, rules, rubric):
    data = content("s01_idp_camp_access")
    data["timing"] = {"phases": [], "warnings": []}  # what the editor's form leaves behind: the built-in behaviour
    assert validate(data, rules, rubric) == []
    for timing in ({"warnings": [0]}, {"warnings": [5, 5]}, {"on_timeout": "explode"}, {"colour": 1}):
        data["timing"] = timing
        assert validate(data, rules, rubric), timing


def test_silence_stages_that_forbid_twists_and_a_trainer_decided_timeout_validate(content, rules, rubric):
    data = content("s01_idp_camp_access")
    data["timing"] = {
        "on_timeout": "trainer",
        "phases": [
            {"id": "formal", "instruction": "Be formal.", "until_turn": 2, "allow_injects": False},
            {"id": "open", "instruction": "Talk."},
        ],
        "silence": {"after_seconds": 45, "line": "Is there more?", "penalty": 10},
    }
    assert validate(data, rules, rubric) == []
    data["timing"]["silence"] = {}  # what the editor leaves behind
    assert validate(data, rules, rubric) == []


def test_bad_silence_rules_are_refused(content, rules, rubric):
    data = content("s01_idp_camp_access")
    for silence in (
        {"after_seconds": 5},
        {"after_seconds": 700},
        {"penalty": 0},
        {"penalty": 99},
        {"line": ""},
        {"colour": 1},
    ):
        data["timing"] = {"silence": silence}
        assert validate(data, rules, rubric), silence
    data["timing"] = {"phases": [{"id": "a", "instruction": "x", "allow_injects": "no"}]}
    assert validate(data, rules, rubric)


def test_classifier_moves_overrides_validation(content, rules, rubric):
    data = content("s01_idp_camp_access")
    data["overrides"] = {"classifier_moves": {"argues_principles_only": False, "opens_with_tier3": True}}
    assert validate(data, rules, rubric) == []

    data["overrides"] = {"classifier_moves": "not_a_dict"}
    issues = validate(data, rules, rubric)
    assert any("mapping of move toggles" in i.message for i in issues)

    data["overrides"] = {"classifier_moves": {"nonexistent_move": False}}
    issues = validate(data, rules, rubric)
    assert any("unknown move nonexistent_move" in i.message for i in issues)

    data["overrides"] = {"classifier_moves": {"argues_principles_only": "not_a_bool"}}
    issues = validate(data, rules, rubric)
    assert any("expected a boolean" in i.message for i in issues)


def test_score_scale_validation(content, rules, rubric):
    data = content("s01_idp_camp_access")
    data["rubric"]["score_scale"] = {"min": 1, "max": 7, "labels": {"1": "Low", "7": "High"}}
    assert validate(data, rules, rubric) == []

    # min >= max
    data["rubric"]["score_scale"] = {"min": 5, "max": 5}
    issues = validate(data, rules, rubric)
    assert any("must be less than max" in i.message for i in issues)

    # label outside min..max
    data["rubric"]["score_scale"] = {"min": 1, "max": 5, "labels": {"6": "Too high"}}
    issues = validate(data, rules, rubric)
    assert any("outside scale 1..5" in i.message for i in issues)

    # non-integer label key
    data["rubric"]["score_scale"] = {"min": 1, "max": 5, "labels": {"bad": "Invalid"}}
    issues = validate(data, rules, rubric)
    assert any("is not an integer" in i.message for i in issues)


def test_reflection_questions_validation(content, rules, rubric):
    data = content("s01_idp_camp_access")
    data["reflection"] = {
        "questions": [
            {"id": "q1", "prompt": "Did you ask questions?"},
            {"id": "q2", "prompt": "Did you listen?"},
        ]
    }
    assert validate(data, rules, rubric) == []

    # duplicate id
    data["reflection"] = {
        "questions": [
            {"id": "q1", "prompt": "First prompt"},
            {"id": "q1", "prompt": "Duplicate prompt"},
        ]
    }
    issues = validate(data, rules, rubric)
    assert any("question id q1 appears twice" in i.message for i in issues)


def test_confidential_between_rejects_unknown_party_ids(content, rules, rubric):
    raw = content("s08_tripartite_siege")
    raw["multiparty"]["confidential_between"] = [
        {"term": "tunnel coordinates", "between": ["opposition_commander"]},  # typo: no such party
        {"term": "general staff offensive", "between": ["gov_colonel", "sheikh_khalil"]},  # counterpart + stakeholder
    ]
    problems = validate(raw, rules, rubric)
    assert any("opposition_commander" in issue.message for issue in problems)
    assert not any("gov_colonel" in issue.message or "sheikh_khalil" in issue.message for issue in problems)


def test_deep_condition_is_refused_before_recursive_schema_validation(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    condition = {"trust_gte": 50}
    for _ in range(180):
        condition = {"all": [condition]}
    raw["outcomes"][0]["when"] = condition
    issues = validate(raw, rules, rubric)
    assert issues
    assert "depth" in issues[0].message.lower()


def test_schema_errors_have_a_bounded_response(content, rules, rubric):
    raw = content("s01_idp_camp_access")
    raw["counterparts"] = [{"id": i} for i in range(500)]
    assert 1 <= len(validate(raw, rules, rubric)) <= 50
