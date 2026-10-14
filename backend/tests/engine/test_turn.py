from nlab.engine.models import Scenario
from nlab.engine.ops import end, grant, inject, is_red_line, nudge, set_dial, start, step
from nlab.engine.state import Classification, Cue, Outcome
from tests.engine.support import ASKS, QUIET, said


def test_moves_and_auto_injection_are_deterministic(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = start(sc, rules).state
    before = state.model_copy(deep=True)
    result = step(
        sc,
        rules,
        state,
        "I hear your concern. What worries you?",
        said(
            ("asks_good_question", "What worries you?"),
            ("shows_respect_curiosity", "I hear your concern"),
            ("identifies_interest", "your concern"),
        ),
    ).state
    assert state == before
    assert result.dials["trust"] == 53
    assert [item.id for item in result.injections] == ["bribe"]
    assert result.injections[0].source == "auto"
    assert "loss_of_control" in result.revealed
    again = step(sc, rules, result, "Tell me more.", QUIET).state
    assert [item.id for item in again.injections] == ["bribe"]


def test_outcome_comes_from_rules_and_red_line_wins(scenario, rules):
    sc = scenario("s09_hostile_checkpoint")
    state = start(sc, rules).state
    state = set_dial(state, "trust", 75).state
    state = set_dial(state, "rigidity", 35).state
    state = set_dial(state, "hostility", 25).state
    first = step(sc, rules, state, "Can we agree to passage?", ASKS).state
    assert (
        first.outcome is None and first.offered is not None and first.offered.id == "passage"
    )  # asking is not agreeing
    assert any(cue.kind == "offer" for cue in first.cues) and not any(cue.kind == "agree_now" for cue in first.cues)
    assert grant(sc, first, "You may pass").state.outcome is None  # a yes on the offer's own turn is the cue talking
    asked = step(sc, rules, first, "Yes, we accept.", ASKS).state
    assert any(cue.kind == "agree_now" for cue in asked.cues)
    granted = grant(sc, asked, "You may pass").state
    assert granted.outcome is not None and granted.outcome.id == "passage"
    crossed = step(
        sc,
        rules,
        state,
        "I will pay you.",
        Classification.model_validate(
            {
                "asked_for_goal": True,
                "red_lines": [{"text": "No payment, gift or diversion of cargo to pass", "quote": "pay you"}],
            }
        ),
    ).state
    assert crossed.outcome is not None and crossed.outcome.result == "fail" and crossed.outcome.id == "red_line"
    invented = step(
        sc,
        rules,
        state,
        "I will pay you.",
        Classification.model_validate(
            {"red_lines": [{"text": "A rule the scenario does not have", "quote": "pay you"}]}
        ),
    ).state
    assert invented.outcome is None


def test_proposal_trigger_and_operational_detail(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    result = step(
        sc,
        rules,
        start(sc, rules).state,
        "A liaison may observe distribution. We can agree the route.",
        Classification.model_validate(
            {
                "proposals": [
                    {
                        "issue": "distribution",
                        "side": "counterpart",
                        "line": "bottom_line",
                        "quote": "A liaison may observe distribution",
                    }
                ],
                "operational_details": [{"id": "route", "quote": "agree the route"}],
            }
        ),
    )
    assert "route" in result.state.covered_details
    assert any("consult his commanders" in cue.text for cue in result.state.cues)
    assert any(event.kind == "detail" and event.ref == "route" for event in result.events)


def test_commitment_outside_mandate_is_flagged(scenario, rules):
    sc = scenario("s09_hostile_checkpoint")
    state = step(
        sc,
        rules,
        start(sc, rules).state,
        "I will change the convoy route.",
        Classification.model_validate(
            {
                "moves": [{"id": "unauthorized_commitment", "quote": "change the convoy route"}],
                "mandate_breaches": [
                    {"text": "Changing the convoy route or cargo", "quote": "change the convoy route"}
                ],
            }
        ),
    ).state
    assert state.flags[-1].id == "mandate_breach"


def test_trainer_actions_never_decide_the_outcome_directly(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = set_dial(start(sc, rules).state, "hostility", 95).state
    state = inject(sc, state, "military_call").state
    assert state.outcome is None  # the trainer steers; the trainee's next message decides
    after = step(sc, rules, state, "Let us continue.", QUIET).state
    assert after.outcome is not None and after.outcome.id == "refused"


def test_ready_outcome_is_offered_once_and_accepting_closes_it(scenario, rules):
    sc = scenario("s09_hostile_checkpoint")  # partial: trust>=45, rigidity<=70, hostility<=65; success: 65/50/50
    state = start(sc, rules).state
    state.dials.update(trust=30, rigidity=60, hostility=40)
    assert step(sc, rules, state, "Hello.", QUIET).state.offered is None  # numbers not in range yet

    state.dials.update(trust=60)  # partial range, success not
    offered = step(sc, rules, state, "Tell me more.", QUIET).state
    assert offered.offered is not None and offered.offered.id == "safe_next_step" and offered.offered.turn == 1
    assert any(cue.kind == "offer" for cue in offered.cues)
    assert offered.outcome is None  # nobody asked for it, so the session is still open

    again = step(sc, rules, offered, "Go on.", QUIET).state
    assert again.offered is not None and again.offered.turn == 1  # still pending from turn 1
    assert any(cue.kind == "offer" for cue in again.cues)  # still cued while pending

    again.dials.update(trust=70, rigidity=45)  # success range now: a fresh, better offer
    better = step(sc, rules, again, "I see.", QUIET).state
    assert better.offered is not None and better.offered.id == "passage"
    assert any(cue.kind == "offer" for cue in better.cues)

    accepted = step(sc, rules, better, "Yes, please let us pass.", ASKS).state
    assert accepted.outcome is None and accepted.offered is not None and accepted.offered.id == "passage"
    assert Cue(kind="agree_now", label="Convoy passage agreed") in accepted.cues  # the counterpart is told to answer
    granted = grant(sc, accepted, "Agreed, you may pass").state
    assert granted.outcome is not None and granted.outcome.id == "passage"


def test_a_partial_outcome_is_a_milestone_and_only_the_goal_ends_the_session(scenario, rules):
    sc = scenario("s09_hostile_checkpoint")
    state = start(sc, rules).state
    state.dials.update(trust=55, rigidity=60, hostility=40)  # partial range only
    state = step(sc, rules, step(sc, rules, state, "Tell me more.", QUIET).state, "Yes, that works.", ASKS).state
    assert state.offered is not None and state.offered.id == "safe_next_step"
    milestone = grant(sc, state, "Agreed, a confirmation procedure")
    state = milestone.state
    assert state.outcome is None and [item.id for item in state.reached] == ["safe_next_step"] and state.offered is None
    assert milestone.events[-1].kind == "grant"

    state = step(sc, rules, state, "Thank you.", QUIET).state
    assert state.outcome is None and state.offered is None  # not offered again
    assert Cue(kind="reached", label="Safe confirmation procedure agreed") in state.cues

    state.dials.update(trust=70, rigidity=45, hostility=30)  # now the goal is in range
    state = step(sc, rules, step(sc, rules, state, "I see.", QUIET).state, "Yes, please let us pass.", ASKS).state
    assert state.offered is not None and state.offered.id == "passage"
    done = grant(sc, state, "You may pass").state
    assert done.outcome is not None and done.outcome.id == "passage" and len(done.reached) == 1


def test_which_endings_count_as_a_red_line():
    assert is_red_line(Outcome(id="red_line", label="Red line crossed", result="fail", turn=1))
    assert is_red_line(Outcome(id="insult", label="Red line crossed: insult", result="fail", turn=1))
    assert not is_red_line(Outcome(id="turned_around", label="Convoy turned around", result="fail", turn=1))
    assert not is_red_line(Outcome(id="passage", label="Convoy passage agreed", result="success", turn=1))
    assert not is_red_line(None)


def test_the_counterparts_yes_ends_the_session_only_if_the_numbers_still_support_it(scenario, rules):
    sc = scenario("s09_hostile_checkpoint")
    state = start(sc, rules).state
    state.dials.update(trust=70, rigidity=45, hostility=30)
    ready = step(sc, rules, state, "We carry food.", QUIET).state
    assert ready.offered is not None and ready.offered.id == "passage" and ready.outcome is None

    assert grant(sc, ready, "You may pass").state.outcome is None  # offered this very turn: too early
    ready = step(sc, rules, ready, "Yes, please.", ASKS).state
    granted = grant(sc, ready, "You may pass")
    assert granted.state.outcome == Outcome(id="passage", label="Convoy passage agreed", result="success", turn=2)
    assert granted.state.offered is None
    assert granted.events[-1].kind == "grant" and granted.events[-1].quote == "You may pass"
    assert ready.outcome is None  # the input state is not modified

    ready.dials["trust"] = 30  # the trainer pulled trust down after the offer was cued
    assert grant(sc, ready, "You may pass").state.outcome is None
    assert grant(sc, start(sc, rules).state, "You may pass").state.outcome is None  # nothing was on the table


def test_each_turns_cues_are_reported_as_events(scenario, rules):
    sc = scenario("detention_police_station")
    first = step(
        sc,
        rules,
        start(sc, rules).state,
        "You have a legal obligation to let us see him.",
        said(("argues_principles_only", "legal obligation")),
    )
    logged = [event.cue for event in first.events if event.kind == "cue"]
    lecture = Cue(kind="hint", text="Do not lecture me about the law in my own station.")
    assert logged == first.state.cues and lecture in logged
    assert all(event.turn == 1 for event in first.events if event.kind == "cue")
    second = step(sc, rules, first.state, "Good afternoon, Captain.", QUIET).state
    assert lecture not in second.cues  # cues are per turn


def test_start_returns_the_opening_line(scenario, rules, content):
    sc = scenario("s01_idp_camp_access")
    begun = start(sc, rules)
    assert begun.opening == (
        content("s01_idp_camp_access")["counterparts"][0].get("opening") or sc.counterpart.stated_position
    )
    assert begun.state.turn == 0 and begun.state.dials["consistency"] == 100


def test_the_opening_state_keeps_the_speaking_counterpart(scenario, rules):
    """The opening line is stored with the start state as its speaker, so every transcript line can be named:
    a single-party session talks to one counterpart the whole time, named from turn 0 on."""
    sc = scenario("detention_police_station")  # one counterpart, no stakeholders
    begun = start(sc, rules)
    assert begun.state.active_interlocutor == "police_captain"
    first = step(sc, rules, begun.state, "Good evening, Captain.", QUIET).state
    assert first.active_interlocutor == "police_captain"


def test_the_nudge_instruction_names_both_sides_of_the_silence(scenario, rules):
    """The inactivity prompt must say who speaks to whom: without that, the counterpart's model reached for
    its own rank as the trainee's vocative ("Captain. ..." in session f2f911f3-2b09-4b84-a82a-9a23cd11a82b)."""
    sc = scenario("detention_police_station")
    state = nudge(sc, rules, start(sc, rules).state).state
    instruction = state.injections[-1].instruction
    assert "The delegate (the person you are speaking with)" in instruction


def test_the_player_can_end_the_session_once(scenario, rules):
    sc = scenario("s01_idp_camp_access")
    ended = end(start(sc, rules).state)
    assert ended.state.outcome is not None and ended.state.outcome.result == "ended"
    assert ended.events[-1].kind == "ended"


def test_a_red_line_emits_flag_and_outcome_events(scenario, rules):
    sc = scenario("s09_hostile_checkpoint")
    result = step(
        sc,
        rules,
        start(sc, rules).state,
        "I will pay you.",
        Classification.model_validate(
            {"red_lines": [{"text": "No payment, gift or diversion of cargo to pass", "quote": "pay you"}]}
        ),
    )
    kinds = [(event.kind, event.ref) for event in result.events]
    assert ("flag", "red_line_crossed") in kinds and ("outcome", "red_line") in kinds
    flag = next(event for event in result.events if event.kind == "flag")
    assert flag.quote == "pay you" and flag.text == "No payment, gift or diversion of cargo to pass"


def test_a_level_shift_emits_a_level_event(content, rules):
    raw = content("s01_idp_camp_access")
    raw["triggers"] = [{"when": {"move": "asks_good_question"}, "shift_level": "political"}]
    sc = Scenario.from_content(raw)
    result = step(
        sc, rules, start(sc, rules).state, "What worries you?", said(("asks_good_question", "What worries you?"))
    )
    assert result.state.level == "political"
    assert any(event.kind == "level" and event.reason == "political" for event in result.events)


def test_classifier_moves_can_be_disabled_per_scenario(content, rules):
    raw = content("s01_idp_camp_access")
    raw["overrides"] = {"classifier_moves": {"asks_good_question": False}}
    sc = Scenario.from_content(raw)
    state = start(sc, rules).state
    result = step(
        sc,
        rules,
        state,
        "What worries you?",
        said(("asks_good_question", "What worries you?")),
    ).state
    # asks_good_question normally increases trust (+2), but here it was disabled
    assert result.dials["trust"] == state.dials["trust"]
    assert "asks_good_question" not in [m.id for m in result.moves]
