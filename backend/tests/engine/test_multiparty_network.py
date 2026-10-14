"""Tests for CCHN Phase 7: Multi-Party Negotiation, Network Play (T12), and Self-Reflection."""

from nlab.engine.cchn_debrief import compute_cchn_debrief
from nlab.engine.models import Scenario
from nlab.engine.ops import nudge, start, step
from nlab.engine.state import Classification, ItemEvidence, State


def test_s08_tripartite_loads_and_starts(content, rules):
    raw = content("s08_tripartite_siege")
    scenario = Scenario.from_content(raw)

    assert len(scenario.counterparts) == 2
    assert scenario.counterparts[0].id == "gov_colonel"
    assert scenario.counterparts[1].id == "opposition_cmdr"
    assert len(scenario.stakeholders) == 2
    assert scenario.multiparty is not None
    assert "tunnel coordinates" in [entry.term for entry in scenario.multiparty.confidential_between]

    begun = start(scenario, rules)
    assert begun.openings is not None
    assert "gov_colonel" in begun.openings
    assert "opposition_cmdr" in begun.openings
    assert begun.state.active_interlocutor == "gov_colonel"
    assert "gov_colonel" in begun.state.counterpart_dials
    assert "opposition_cmdr" in begun.state.counterpart_dials


def test_multiparty_distinct_dials_and_switching(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    begun = start(scenario, rules)
    state = begun.state

    # Initial dials
    assert state.counterpart_dials["gov_colonel"]["rigidity"] == 80
    assert state.counterpart_dials["opposition_cmdr"]["rigidity"] == 75

    # Trainee uses positive move with gov_colonel
    # e.g. identifies_interest: trust +10, rigidity -10, hostility -5
    c1 = Classification(
        moves=[ItemEvidence(id="identifies_interest", quote="I understand your concerns about security")]
    )
    s1 = step(scenario, rules, state, "I understand your concerns about security", c1, interlocutor="gov_colonel")

    # gov_colonel dials changed (identifies_interest: rigidity -15)
    assert s1.state.counterpart_dials["gov_colonel"]["rigidity"] == 65
    # opposition_cmdr dials unaffected
    assert s1.state.counterpart_dials["opposition_cmdr"]["rigidity"] == 75

    # Switch to opposition_cmdr
    c2 = Classification(
        moves=[ItemEvidence(id="frames_shared_benefit", quote="We both want to protect civilian lives")]
    )
    s2 = step(scenario, rules, s1.state, "We both want to protect civilian lives", c2, interlocutor="opposition_cmdr")

    assert s2.state.active_interlocutor == "opposition_cmdr"
    # opposition_cmdr rigidity lowered (frames_shared_benefit: rigidity -6)
    assert s2.state.counterpart_dials["opposition_cmdr"]["rigidity"] == 69
    # gov_colonel rigidity remains 65
    assert s2.state.counterpart_dials["gov_colonel"]["rigidity"] == 65


def test_multiparty_confidentiality_breach(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    begun = start(scenario, rules)

    initial_hostility = begun.state.counterpart_dials["gov_colonel"]["hostility"]
    # Leaking confidential term "tunnel coordinates" to gov_colonel
    text = "The opposition told us their tunnel coordinates are near the market"
    c = Classification()
    s = step(scenario, rules, begun.state, text, c, interlocutor="gov_colonel")

    # Hostility surges by 25 due to confidentiality breach
    assert s.state.counterpart_dials["gov_colonel"]["hostility"] == initial_hostility + 25
    assert any(flag.id == "confidentiality_breach" for flag in s.state.flags)
    assert any("confidential information" in cue.text.lower() for cue in s.state.cues)


def test_network_play_stakeholder_influence(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    begun = start(scenario, rules)
    state = begun.state

    # Sheikh Khalil has influence: high (-20 rigidity, -15 hostility across all counterparts)
    initial_gov_rig = state.counterpart_dials["gov_colonel"]["rigidity"]
    initial_opp_rig = state.counterpart_dials["opposition_cmdr"]["rigidity"]

    # Trainee engages Sheikh Khalil with constructive principle translation move
    c = Classification(
        moves=[ItemEvidence(id="translates_principle", quote="Our religion and culture demand mercy for the starving")]
    )
    text = "Our religion and culture demand mercy for the starving"
    s = step(scenario, rules, state, text, c, interlocutor="sheikh_khalil")

    # Engagement tracked
    assert s.state.stakeholder_engagements.get("sheikh_khalil") == 1

    # Influence applied to both counterparts: rigidity -20
    assert s.state.counterpart_dials["gov_colonel"]["rigidity"] == initial_gov_rig - 20
    assert s.state.counterpart_dials["opposition_cmdr"]["rigidity"] == initial_opp_rig - 20
    assert any("influence" in cue.text.lower() for cue in s.state.cues)

    # 2nd engagement: diminishing returns (multiplier 0.5 -> -10 rigidity)
    s2 = step(scenario, rules, s.state, text, c, interlocutor="sheikh_khalil")
    assert s2.state.stakeholder_engagements.get("sheikh_khalil") == 2
    assert s2.state.counterpart_dials["gov_colonel"]["rigidity"] == initial_gov_rig - 30
    assert s2.state.counterpart_dials["opposition_cmdr"]["rigidity"] == initial_opp_rig - 30

    # 3rd engagement: capped (multiplier 0.0 -> no change, maximum influence cue)
    s3 = step(scenario, rules, s2.state, text, c, interlocutor="sheikh_khalil")
    assert s3.state.stakeholder_engagements.get("sheikh_khalil") == 3
    assert s3.state.counterpart_dials["gov_colonel"]["rigidity"] == initial_gov_rig - 30
    assert s3.state.counterpart_dials["opposition_cmdr"]["rigidity"] == initial_opp_rig - 30
    assert any("already leveraged maximum influence" in cue.text.lower() for cue in s3.state.cues)


def test_stakeholder_confidentiality_breach(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    begun = start(scenario, rules)
    init_gov_host = begun.state.counterpart_dials["gov_colonel"]["hostility"]
    init_opp_host = begun.state.counterpart_dials["opposition_cmdr"]["hostility"]

    text = "We have the secret tunnel coordinates from the other party."
    c = Classification()
    s = step(scenario, rules, begun.state, text, c, interlocutor="sheikh_khalil")

    assert any(flag.id == "confidentiality_breach" for flag in s.state.flags)
    assert s.state.counterpart_dials["gov_colonel"]["hostility"] == init_gov_host + 25
    assert s.state.counterpart_dials["opposition_cmdr"]["hostility"] == init_opp_host + 25


def test_debrief_includes_fh_reflection_questions(content, rules):
    raw = content("s08_tripartite_siege")
    state = State(
        scenario_id="s08_tripartite_siege",
        dials={"trust": 50, "rigidity": 50, "hostility": 50},
        level="technical",
    )
    debrief = compute_cchn_debrief(
        content=raw,
        state=state,
        turns=[],
        preparation=None,
        reflection=None,
        session_debrief=None,
    )
    assert debrief.reflection is not None
    q_ids = [q.id for q in debrief.reflection.questions]
    assert "fh_conflict_style" in q_ids
    assert "fh_challenge_or_dilemma" in q_ids


def test_confidential_term_is_safe_with_its_owner(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    begun = start(scenario, rules)

    # "tunnel coordinates" is confidential between the opposition only: repeating it TO them is no breach
    text = "You mentioned your tunnel coordinates; let us talk about the convoy instead."
    s = step(scenario, rules, begun.state, text, Classification(), interlocutor="opposition_cmdr")
    assert not any(flag.id == "confidentiality_breach" for flag in s.state.flags)


def test_confidential_term_breaches_with_a_third_party(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    begun = start(scenario, rules)

    # ...but telling the government commander the opposition's term is a breach
    text = "We know the tunnel coordinates near the market."
    s = step(scenario, rules, begun.state, text, Classification(), interlocutor="gov_colonel")
    assert any(flag.id == "confidentiality_breach" for flag in s.state.flags)


def test_legacy_string_terms_stay_confidential_toward_everyone(content, rules):
    raw = content("s08_tripartite_siege")
    raw["multiparty"]["confidential_between"] = ["tunnel coordinates"]
    scenario = Scenario.from_content(raw)
    begun = start(scenario, rules)

    text = "You mentioned your tunnel coordinates; let us talk about the convoy instead."
    s = step(scenario, rules, begun.state, text, Classification(), interlocutor="opposition_cmdr")
    assert any(flag.id == "confidentiality_breach" for flag in s.state.flags)


def test_stakeholder_dials_persist_across_switches(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    state = start(scenario, rules).state
    sh = "sheikh_khalil"
    assert sh in state.counterpart_dials  # seeded from the scenario baseline at start

    initial_trust = state.counterpart_dials[sh]["trust"]
    move = Classification(moves=[ItemEvidence(id="acknowledges_emotion", quote="I hear how heavy this is")])
    for _ in range(5):
        state = step(scenario, rules, state, "I hear how heavy this is for the town", move, interlocutor=sh).state

    # acknowledges_emotion: hostility -8, rigidity -4 (no trust delta) -> use a trust move for the assertion
    trust_move = Classification(moves=[ItemEvidence(id="identifies_interest", quote="What matters most to you")])
    state = step(scenario, rules, state, "What matters most to you here?", trust_move, interlocutor=sh).state
    trust_after = state.counterpart_dials[sh]["trust"]
    assert trust_after > initial_trust

    # switch to a commander, then back: the stakeholder's trust is kept, and shown while active
    state = step(
        scenario, rules, state, "Colonel, about the checkpoint", Classification(), interlocutor="gov_colonel"
    ).state
    assert state.counterpart_dials[sh]["trust"] == trust_after
    state.active_interlocutor = sh  # what set_interlocutor does
    state.dials = dict(state.counterpart_dials[sh])
    state = step(scenario, rules, state, "We meet again, Sheikh", Classification(), interlocutor=sh).state
    assert state.counterpart_dials[sh]["trust"] == trust_after


def test_stakeholder_turns_never_offer_or_grant_outcomes(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    state = start(scenario, rules).state
    sh = "sheikh_khalil"

    constructive = Classification(
        asked_for_goal=True,
        moves=[ItemEvidence(id="identifies_interest", quote="What matters most to the town")],
    )
    for _ in range(10):
        state = step(scenario, rules, state, "What matters most to the town?", constructive, interlocutor=sh).state
        assert state.offered is None
        assert state.outcome is None

    # the counterparts' own dials are nowhere near an agreement: only the network bonus moved them
    assert state.counterpart_dials["gov_colonel"]["trust"] < 40


def test_stakeholder_turns_reveal_no_counterpart_interests(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    state = start(scenario, rules).state
    sh = "sheikh_khalil"

    probing = Classification(moves=[ItemEvidence(id="identifies_interest", quote="What do you need")])
    for _ in range(4):
        state = step(scenario, rules, state, "What do you need most?", probing, interlocutor=sh).state

    assert state.revealed == []
    assert state.counterpart_revealed["gov_colonel"] == []
    assert state.counterpart_revealed["opposition_cmdr"] == []


def test_pre_pr_state_seeds_a_stakeholder_named_directly_on_a_turn(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    state = start(scenario, rules).state
    # a stored state from before stakeholders had entries: counterparts only, colonel active
    state.counterpart_dials = {
        pid: dials for pid, dials in state.counterpart_dials.items() if pid in ("gov_colonel", "opposition_cmdr")
    }
    sh = "sheikh_khalil"

    move = Classification(moves=[ItemEvidence(id="identifies_interest", quote="What matters most to you")])
    state = step(scenario, rules, state, "What matters most to you?", move, interlocutor=sh).state

    assert sh in state.counterpart_dials  # seeded on first contact even without a prior switch
    assert state.counterpart_dials[sh]["trust"] > state.counterpart_dials["gov_colonel"]["trust"]
    # ...and it survives a later switch, because it is a real entry now
    state = step(scenario, rules, state, "Colonel?", Classification(), interlocutor="gov_colonel").state
    kept = state.counterpart_dials[sh]["trust"]
    assert kept > 25  # the colonel's baseline the entry was seeded from


def test_a_nudge_while_a_stakeholder_is_selected_offers_and_reveals_nothing(content, rules):
    scenario = Scenario.from_content(content("s08_tripartite_siege"))
    state = start(scenario, rules).state
    sh = "sheikh_khalil"

    constructive = Classification(moves=[ItemEvidence(id="identifies_interest", quote="What matters most")])
    for _ in range(4):
        state = step(scenario, rules, state, "What matters most?", constructive, interlocutor=sh).state

    state = nudge(scenario, rules, state).state
    assert state.offered is None
    assert state.outcome is None
    assert state.revealed == []
    assert state.counterpart_revealed["gov_colonel"] == []


def test_a_nudge_while_a_stakeholder_is_selected_offers_nothing_imn(content, rules):
    scenario = Scenario.from_content(content("imn_detainee_access_network"))
    state = start(scenario, rules).state
    sh = "sheikh_zubair"

    constructive = Classification(moves=[ItemEvidence(id="identifies_interest", quote="What matters most")])
    for _ in range(4):
        state = step(scenario, rules, state, "What matters most?", constructive, interlocutor=sh).state

    state = nudge(scenario, rules, state).state
    assert state.offered is None
    assert state.outcome is None
    assert state.revealed == []


def test_trigger_shift_level_fires_for_counterparts_but_not_stakeholders(content, rules):
    raw = content("s08_tripartite_siege")
    raw["negotiation"]["start_level"] = "technical"
    raw["triggers"] = [{"when": {"trust_gte": 50}, "shift_level": "political", "say": "The mood shifts."}]

    constructive = Classification(moves=[ItemEvidence(id="identifies_interest", quote="What matters most")])
    # a stakeholder's own trust crossing 50 must not move the session-wide level
    scenario = Scenario.from_content(raw)
    state = start(scenario, rules).state
    for _ in range(6):  # identifies_interest: trust +5 per turn, from 25
        state = step(scenario, rules, state, "What matters most?", constructive, interlocutor="sheikh_khalil").state
    assert state.counterpart_dials["sheikh_khalil"]["trust"] >= 50
    assert state.level == "technical"

    # the same threshold with a counterpart fires as before
    state = start(Scenario.from_content(raw), rules).state
    for _ in range(6):
        state = step(scenario, rules, state, "What matters most?", constructive, interlocutor="gov_colonel").state
    assert state.counterpart_dials["gov_colonel"]["trust"] >= 50
    assert state.level == "political"
