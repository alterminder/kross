from types import SimpleNamespace

from nlab.engine.cchn_debrief import (
    compute_agreement_check,
    compute_cchn_debrief,
    compute_competences,
    compute_deescalation_report,
    compute_iceberg_depth,
    compute_level_timeline,
    compute_prep_vs_reality,
    compute_reflection_section,
    compute_zones,
)
from nlab.engine.state import MoveRecord, Outcome, ProposalRecord, State


def test_agreement_check_criteria_and_terms():
    content = {
        "title": "Convoy Access",
        "implementation_checklist": [
            {"id": "truck_count", "text": "Truck count and manifest"},
            {"id": "travel_route", "text": "Designated transit route"},
            {"id": "liaison_officer", "text": "Contact details of field liaison"},
        ],
    }
    state = State(
        scenario_id="s1",
        dials={"trust": 70, "hostility": 20},
        level="technical",
        outcome=Outcome(id="convoy_passed", label="Convoy safely cleared checkpoint", result="success", turn=4),
        covered_details=["truck_count", "travel_route"],
        moves=[MoveRecord(turn=2, id="defines_sequence", quote="we send manifest on day 1")],
        proposals=[ProposalRecord(turn=3, issue="route", side="trainee", line="southern_corridor", quote="south")],
    )
    turn1 = SimpleNamespace(number=1, trainee_text="Hello, we have a liaison hotline to discuss any misunderstanding")
    turns = [turn1]

    agreement = compute_agreement_check(content, state, turns)
    assert agreement.is_deal is True
    assert len(agreement.terms_sheet) >= 3
    assert len(agreement.criteria) == 5
    assert agreement.criteria[0].id == "clear_language"
    assert agreement.criteria[0].status in ("met", "partial")
    assert agreement.criteria[2].id == "reciprocity_and_sequence"
    assert agreement.criteria[2].status == "met"
    assert agreement.criteria[3].id == "divergence_process"
    assert agreement.criteria[3].status == "met"
    assert agreement.overall_score > 50


def test_zones_and_tier_3_parking():
    content = {
        "title": "Access Scenario",
        "counterparts": [
            {
                "iceberg": {
                    "position": {"stated": "No trucks allowed without military escort"},
                }
            }
        ],
        "issues": [
            {"id": "escort", "text": "Armed military escort", "tier": 1},
            {"id": "political_allegiance", "text": "Public statement supporting local council", "tier": 3},
        ],
    }
    state = State(
        scenario_id="s1",
        dials={"trust": 65},
        level="professional",
        outcome=Outcome(id="deal", label="Access granted with neutral monitoring", result="success", turn=5),
        flags=[],
        proposals=[ProposalRecord(turn=3, issue="escort", side="trainee", line="neutral_monitors", quote="")],
    )

    zones = compute_zones(content, state)
    assert zones.zone == "E"
    assert "Common Shared Space" in zones.zone_label
    assert zones.tier_3_parked is True
    assert len(zones.tier_3_issues) == 1
    assert zones.tier_3_issues[0].status == "parked"


def test_level_timeline_tracking():
    content = {
        "negotiation": {"start_level": "technical"},
    }
    state = State(scenario_id="s1", dials={}, level="political")
    turn0 = SimpleNamespace(number=0, reply_text="What are your logistics?")
    turn1 = SimpleNamespace(
        number=1,
        trainee_text="We bring food",
        engine_state_after={"level": "technical"},
        classification={"moves": []},
    )
    turn2 = SimpleNamespace(
        number=2,
        trainee_text="This touches on international humanitarian law principles",
        engine_state_after={"level": "political"},
        classification={"moves": ["politicizes", "appeals_to_principles"]},
    )
    turns = [turn0, turn1, turn2]

    timeline = compute_level_timeline(content, state, turns)
    assert timeline.start_level == "technical"
    assert timeline.final_level == "political"
    assert len(timeline.entries) == 3
    assert timeline.entries[2].shifted is True
    assert timeline.entries[2].direction == "politicize"
    assert timeline.entries[2].speaker == "trainee"


def test_iceberg_depth_vs_prep_guesses():
    content = {
        "counterparts": [
            {
                "iceberg": {
                    "position": {"stated": "We will not grant entry"},
                },
                "hidden_interests": [
                    {"id": "fuel_shortage", "layer": "reasoning", "text": "Local community lacks fuel"},
                    {
                        "id": "commander_honor",
                        "layer": "motives_values",
                        "text": "Fear of losing status in front of elders",
                    },
                ],
            }
        ]
    }
    state = State(
        scenario_id="s1",
        dials={},
        level="technical",
        turn=3,
        revealed=["fuel_shortage"],
    )
    preparation = {
        "counterpart_iceberg": {
            "what": "Refusal to allow passage",
            "how": "Needs local resources or fuel",
            "why": "Tribal elder respect",
        }
    }

    depth = compute_iceberg_depth(content, state, preparation)
    assert depth.max_layer_reached == "reasoning"
    assert len(depth.layers) == 3
    assert depth.layers[0].reached is True
    assert depth.layers[1].reached is True
    assert depth.layers[2].reached is False
    assert depth.layers[1].prep_guess == "Needs local resources or fuel"


def test_deescalation_report():
    turn1 = SimpleNamespace(
        number=1,
        reply_text="You people never listen! I am angry and refuse your convoy!",
        engine_state_after={"dials": {"hostility": 70}},
    )
    turn2 = SimpleNamespace(
        number=2,
        trainee_text=(
            "I hear and acknowledge your frustration. If I understand correctly, the core issue "
            "is timing. What options could we consider together?"
        ),
        engine_state_after={"dials": {"hostility": 35}},
    )
    turns = [turn1, turn2]

    report = compute_deescalation_report(turns)
    assert len(report.incidents) == 1
    inc = report.incidents[0]
    assert inc.hostility_level == 70
    assert inc.hostility_after == 35
    assert inc.outcome == "de-escalated"
    assert any("Pause & acknowledge emotion" in s for s in inc.steps_observed)
    assert any("Reformulate" in s for s in inc.steps_observed)
    assert any("Discuss options" in s for s in inc.steps_observed)


def test_reflection_and_competences_and_master_cchn():
    reflection_data = {
        "answers": {
            "t6_counterpart_perspective": "We actively listened first.",
            "t6_options_under_resistance": "We offered three routing choices.",
            "t6_clear_next_steps": "We agreed on a phone liaison before departure.",
        }
    }
    reflection = compute_reflection_section(reflection_data)
    assert reflection.completed is True
    assert len(reflection.questions) == 3

    content = {
        "title": "Scenario 1",
        "rubric": {
            "dimensions": ["context_analysis", "options_generation", "mandate_integrity"],
        },
    }
    turn = SimpleNamespace(
        number=1,
        scores={"scores": [{"id": "context_analysis", "score": 5}, {"id": "options_generation", "score": 4}]},
    )
    competences = compute_competences(content, [turn], session_debrief=None)
    assert len(competences.tiers) == 3
    assert competences.tiers[0].tier == "core"
    assert competences.tiers[1].tier == "advanced"
    assert competences.tiers[2].tier == "expert"

    state = State(scenario_id="s1", dials={"trust": 50}, level="technical")
    master = compute_cchn_debrief(
        content,
        state,
        [turn],
        preparation=None,
        reflection=reflection_data,
        session_debrief=None,
    )
    assert master.agreement_check is not None
    assert master.zones is not None
    assert master.level_timeline is not None
    assert master.iceberg_depth is not None
    assert master.deescalation_report is not None
    assert master.prep_vs_reality is not None
    assert master.reflection.completed is True
    assert master.competences is not None
    assert len(master.knowledge_links) == 8


def test_cchn_debrief_sections_filtering():
    content = {
        "id": "s1",
        "debrief": {"sections": ["agreement_check", "reflection"]},
    }
    state = State(scenario_id="s1", dials={"trust": 50}, level="technical")
    master = compute_cchn_debrief(
        content,
        state,
        [],
        preparation=None,
        reflection=None,
        session_debrief=None,
    )
    assert master.agreement_check is not None
    assert master.reflection is not None
    assert master.zones is None
    assert master.level_timeline is None
    assert master.iceberg_depth is None
    assert master.deescalation_report is None
    assert master.prep_vs_reality is None
    assert master.competences is None
    assert len(master.knowledge_links) == 2


def test_cchn_debrief_custom_reflection_questions():
    content = {
        "id": "s1",
        "reflection": {
            "questions": [
                {"id": "q_team", "prompt": "Did you coordinate with the team?", "guidance": "Teamwork"},
            ]
        },
    }
    state = State(scenario_id="s1", dials={"trust": 50}, level="technical")
    master = compute_cchn_debrief(
        content,
        state,
        [],
        preparation=None,
        reflection={"answers": {"q_team": "Yes, thoroughly."}},
        session_debrief=None,
    )
    assert master.reflection is not None
    assert len(master.reflection.questions) == 1
    assert master.reflection.questions[0].id == "q_team"
    assert master.reflection.questions[0].answer == "Yes, thoroughly."
    assert master.reflection.completed is True


def test_prep_vs_reality_author_key_comparison():
    content = {
        "island_of_agreements": {
            "agreed_facts": ["convoy has 5 trucks"],
            "contested_facts": ["driver identity verified"],
            "convergent_norms": ["humanitarian assistance is neutral"],
        },
        "counterparts": [
            {
                "legitimacy_weights": {"legal": 80, "moral": 40},
                "hidden_interests": [{"id": "hi_1", "text": "fear of ambush"}],
            }
        ],
        "claims": [{"id": "c1", "text": "route is mined"}],
        "stakeholders": [{"id": "sh_1", "role": "Elder"}],
    }
    state = State(scenario_id="s1", dials={"trust": 60}, level="technical", revealed=["hi_1"])
    # 1. Aligned prep: agreed facts matching, legitimacy source matching legal
    prep_aligned = {
        "island_of_agreements": {
            "agreed_facts": ["convoy has 5 trucks"],
            "contested_facts": ["driver identity verified"],
        },
        "level_and_narrative": {"expected_level": "technical"},
        "counterpart_iceberg": {"position": "Halt convoy"},
        "legitimacy_profile": {"emphasis": ["legal"]},
        "information_quality": {"claims_assessment": {"c1": "medium"}},
    }
    res_aligned = compute_prep_vs_reality(content, state, prep_aligned)
    assert res_aligned.has_preparation is True
    mod_map = {m.module_id: m for m in res_aligned.modules}
    assert mod_map["island_of_agreements"].alignment == "aligned"
    assert mod_map["level_and_narrative"].alignment == "aligned"
    assert mod_map["counterpart_iceberg"].alignment == "aligned"
    assert mod_map["legitimacy_profile"].alignment == "aligned"
    assert mod_map["information_quality"].alignment == "aligned"

    # 2. Diverged prep: placing contested fact into agreed facts, mismatched level
    prep_diverged = {
        "island_of_agreements": {
            "agreed_facts": ["driver identity verified"],  # Contested in author key!
        },
        "level_and_narrative": {"expected_level": "political"},  # state is technical!
        "legitimacy_profile": {"emphasis": ["traditional"]},  # counterpart values legal!
    }
    res_diverged = compute_prep_vs_reality(content, state, prep_diverged)
    mod_div_map = {m.module_id: m for m in res_diverged.modules}
    assert mod_div_map["island_of_agreements"].alignment == "diverged"
    assert mod_div_map["level_and_narrative"].alignment == "diverged"
    assert mod_div_map["legitimacy_profile"].alignment == "diverged"


def test_deescalation_canonical_move_evidence():
    turn1 = SimpleNamespace(
        number=1,
        reply_text="You people are arrogant and we refuse your convoy!",
        engine_state_after={"dials": {"hostility": 55}},
    )
    # Turn 2 has classified canonical moves: pause_and_acknowledge (step 1) & oco_questions (step 5)
    # even without matching typical text keywords
    turn2 = SimpleNamespace(
        number=2,
        trainee_text="We appreciate the immense security burden placed upon your units.",
        engine_state_after={
            "dials": {"hostility": 45},
            "moves": [{"id": "pause_and_acknowledge"}, {"id": "oco_questions"}],
        },
        classification={"moves": []},
    )
    report = compute_deescalation_report(turns=[turn1, turn2])
    assert len(report.incidents) == 1
    incident = report.incidents[0]
    assert incident.outcome == "de-escalated"
    assert "1. Pause & acknowledge emotion" in incident.steps_observed
    assert "5. Question O/C/O" in incident.steps_observed


def test_deescalation_a_bare_question_mark_is_not_step_5():
    turn1 = SimpleNamespace(
        number=1,
        reply_text="You people are arrogant and we refuse your convoy!",
        engine_state_after={"dials": {"hostility": 55}},
    )
    turn2 = SimpleNamespace(
        number=2,
        trainee_text="Really? Is that so? What?",
        engine_state_after={"dials": {"hostility": 45}, "moves": []},
        classification={"moves": []},
    )
    report = compute_deescalation_report(turns=[turn1, turn2])
    assert len(report.incidents) == 1
    assert "5. Question O/C/O" not in report.incidents[0].steps_observed


def test_deescalation_compares_the_same_partys_hostility():
    # s08: a spike with the colonel, then a plain greeting to the sheikh (whose own hostility is lower)
    turn1 = SimpleNamespace(
        number=1,
        reply_text="I refuse your convoy!",
        engine_state_after={
            "dials": {"hostility": 60},
            "active_interlocutor": "gov_colonel",
            "counterpart_dials": {"gov_colonel": {"hostility": 60}, "sheikh_khalil": {"hostility": 50}},
        },
    )
    turn2 = SimpleNamespace(
        number=2,
        trainee_text="Sheikh, good morning.",
        engine_state_after={
            "dials": {"hostility": 50},  # the sheikh's entry is now active
            "active_interlocutor": "sheikh_khalil",
            "counterpart_dials": {"gov_colonel": {"hostility": 60}, "sheikh_khalil": {"hostility": 50}},
        },
    )
    report = compute_deescalation_report(turns=[turn1, turn2])
    assert len(report.incidents) == 1
    assert report.incidents[0].outcome == "neutral"  # the colonel is still at 60: nothing de-escalated
