import asyncio
import json

import pytest
from pydantic import SecretStr

from nlab.engine import Classification, grant, start, step
from nlab.llm.config import LLMConfig, RoleConfig
from nlab.llm.counterpart import CounterpartStream, counterpart_request, determine_phase
from nlab.llm.types import Line, NoAnswer, Usage
from tests.llm.fakes import FakeProvider

ASK = Classification(asked_for_goal=True)


def config(**changes):
    return LLMConfig(default=RoleConfig(model="deepseek-flash", api_key=SecretStr("k"), **changes))


def opening(state_request):
    return state_request.messages[0]["content"]


def test_an_ended_session_gets_a_conclusive_closing_instruction(content, scenario, rules):
    sc = scenario("s09_hostile_checkpoint")
    state = start(sc, rules).state
    state.dials.update(trust=70, rigidity=45, hostility=30)
    ready = step(
        sc, rules, step(sc, rules, state, "Can we agree the convoy passes now?", ASK).state, "Yes, we accept.", ASK
    ).state
    agreed = grant(sc, ready, "You may pass").state
    assert agreed.outcome is not None and agreed.outcome.result == "success"
    request = counterpart_request(config(), content("s09_hostile_checkpoint"), agreed, [])
    text = opening(request)
    assert "Agree, and say in one sentence what is agreed" in text and "Do not ask any question" in text
    assert "Never say the meeting is over" not in text
    assert '"dials"' not in text and '"cues"' not in text and request.temperature == 0.4

    ongoing = start(scenario("s01_idp_camp_access"), rules).state
    request = counterpart_request(config(), content("s01_idp_camp_access"), ongoing, [])
    assert "Never say the meeting is over" in opening(request) and '"dials"' in opening(request)
    assert request.temperature == 0.7

    failing = start(sc, rules).state
    failing.dials.update(hostility=95)
    failed = step(sc, rules, failing, "Enough.", Classification()).state
    assert failed.outcome is not None and failed.outcome.result == "fail" and failed.outcome.id != "red_line"
    assert "End the meeting or refuse" in opening(
        counterpart_request(config(), content("s09_hostile_checkpoint"), failed, [])
    )


def test_cues_reach_the_counterpart_as_sentences(content, scenario, rules):
    sc = scenario("s09_hostile_checkpoint")
    state = start(sc, rules).state
    state.dials.update(trust=70, rigidity=45, hostility=30)
    offered = step(sc, rules, state, "We carry food.", Classification()).state
    assert 'You are ready to agree to \\"Convoy passage agreed\\"' in opening(
        counterpart_request(config(), content("s09_hostile_checkpoint"), offered, [])
    )


def test_the_transcript_becomes_the_conversation(content, scenario, rules):
    state = start(scenario("s01_idp_camp_access"), rules).state
    transcript = [
        Line(role="character", text="Who are you?", turn=0),
        Line(role="trainee", text="The convoy lead.", turn=1),
        Line(role="character", text="And?", turn=1),
    ]
    messages = counterpart_request(config(), content("s01_idp_camp_access"), state, transcript).messages
    assert [m["role"] for m in messages] == ["system", "assistant", "user", "assistant", "user"]
    assert messages[-1]["content"] == "(The delegate waits for your response.)"


def test_the_closing_line_can_think_while_normal_turns_do_not(content, scenario, rules):
    settings = config(thinking=False, closing_reasoning_effort="low")
    sc = scenario("s09_hostile_checkpoint")
    ongoing = start(sc, rules).state
    ended_state = start(sc, rules).state
    ended_state.dials.update(hostility=95)
    ended = step(sc, rules, ended_state, "Enough.", Classification()).state
    normal = counterpart_request(settings, content("s09_hostile_checkpoint"), ongoing, [])
    assert normal.thinking is False and normal.reasoning_effort is None
    closing = counterpart_request(settings, content("s09_hostile_checkpoint"), ended, [])
    assert closing.thinking is True and closing.reasoning_effort == "low"


def collect(stream):
    async def run():
        return "".join([part async for part in stream])

    return asyncio.run(run())


def test_the_stream_yields_text_and_records_usage(content, scenario, rules):
    request = counterpart_request(
        config(), content("s01_idp_camp_access"), start(scenario("s01_idp_camp_access"), rules).state, []
    )
    stream = CounterpartStream(
        FakeProvider(streams=[["Then ", "it is settled.", Usage(7, 3)]]), config().for_role("counterpart"), request
    )
    assert collect(stream) == "Then it is settled." and stream.text == "Then it is settled."
    assert stream.record is not None and stream.record.tokens_out == 3 and stream.record.attempts == 1


def test_a_silent_provider_gets_one_retry_then_a_clean_error(content, scenario, rules):
    fast = config(first_word_seconds=0.2)
    request = counterpart_request(
        fast, content("s01_idp_camp_access"), start(scenario("s01_idp_camp_access"), rules).state, []
    )
    provider = FakeProvider(streams=[["HANG"], ["Back ", "again."]])
    stream = CounterpartStream(provider, fast.for_role("counterpart"), request)
    assert collect(stream) == "Back again." and len(provider.requests) == 2 and stream.record.attempts == 2

    provider = FakeProvider(streams=[["HANG"], ["HANG"]])
    stream = CounterpartStream(provider, fast.for_role("counterpart"), request)
    with pytest.raises(NoAnswer, match="gave no answer"):
        collect(stream)
    assert len(provider.requests) == 2 and stream.record is not None and stream.record.outcome == "timeout"


def test_closing_the_reply_early_closes_the_provider_stream(content, scenario, rules):
    closed = []

    class ClosingProvider(FakeProvider):
        async def stream(self, config, request):
            self.requests.append(request)
            try:
                yield "partial"
                await asyncio.sleep(3600)
            finally:
                closed.append(True)

    request = counterpart_request(
        config(), content("s01_idp_camp_access"), start(scenario("s01_idp_camp_access"), rules).state, []
    )
    stream = CounterpartStream(ClosingProvider(), config().for_role("counterpart"), request)

    async def run():
        parts = aiter(stream)
        assert await anext(parts) == "partial"
        await parts.aclose()

    asyncio.run(run())
    assert closed == [True]


def test_negotiation_phases_evolve_across_turns(content, scenario, rules):
    assert determine_phase(0, 15) == "opening"
    assert determine_phase(2, 15) == "opening"
    assert determine_phase(3, 15) == "exploration"
    assert determine_phase(7, 15) == "exploration"
    assert determine_phase(8, 15) == "closing"
    assert determine_phase(12, 15) == "closing"

    sc = scenario("s01_idp_camp_access")
    state = start(sc, rules).state
    req_open = counterpart_request(config(), content("s01_idp_camp_access"), state, [])
    assert '"negotiation_phase": "opening"' in req_open.messages[0]["content"]
    assert "OPENING PHASE" in req_open.messages[0]["content"]

    state.turn = 5
    req_explore = counterpart_request(config(), content("s01_idp_camp_access"), state, [])
    assert '"negotiation_phase": "exploration"' in req_explore.messages[0]["content"]
    assert "EXPLORATION PHASE" in req_explore.messages[0]["content"]

    state.turn = 10
    req_close = counterpart_request(config(), content("s01_idp_camp_access"), state, [])
    assert '"negotiation_phase": "closing"' in req_close.messages[0]["content"]
    assert "CLOSING PHASE" in req_close.messages[0]["content"]


def test_a_scenarios_own_stages_set_the_phase_by_turn_and_the_built_in_ones_remain_the_default(content):
    from nlab.llm.counterpart import PHASE_INSTRUCTIONS, phase_at, phases_of

    plain = content("s01_idp_camp_access")
    assert [phase.id for phase in phases_of(plain)] == ["opening", "exploration", "closing"]
    assert phase_at(plain, 0).instruction == PHASE_INSTRUCTIONS["opening"]
    assert phase_at(plain, 99).id == "closing"
    own = {
        **plain,
        "timing": {
            "phases": [
                {
                    "id": "cold_start",
                    "label": "Cold start",
                    "hint": "He says little.",
                    "instruction": "Say little.",
                    "until_turn": 2,
                },
                {"id": "the_ask", "instruction": "Press for terms."},
            ]
        },
    }
    assert [(p.id, p.label, p.hint) for p in phases_of(own)] == [
        ("cold_start", "Cold start", "He says little."),
        ("the_ask", "The ask", ""),  # the label defaults to the id, tidied
    ]
    assert [phase_at(own, turn).id for turn in (0, 2, 3, 40)] == ["cold_start", "cold_start", "the_ask", "the_ask"]
    assert phase_at(own, 3).instruction == "Press for terms."


def private_of(request):
    import json

    text = opening(request)
    return json.loads(text[text.index("{") :]).get("private"), text


@pytest.mark.parametrize("layer", ["tactical_reasoning", "motive_value"])
@pytest.mark.parametrize("trust", [15, 40, 60])
def test_private_pressures_and_hidden_lines_wait_for_their_hidden_facts(content, scenario, rules, trust, layer):
    import json

    raw = content("detention_police_station")
    raw["counterparts"][0]["hidden_interests"][1]["layer"] = layer
    sc = scenario("detention_police_station")
    state = start(sc, rules).state
    state.dials["trust"] = trust
    state = step(sc, rules, state, "Hello, Captain.", Classification()).state
    private, _ = private_of(counterpart_request(config(), raw, state, []))

    if trust < 60:
        assert "landowner_pressure" not in state.revealed
        assert "landowner" not in json.dumps(private).lower()
        if layer == "tactical_reasoning":
            assert "reasoning" not in private["inner_view"]
    else:
        assert "landowner_pressure" in state.revealed
        assert "The landowner expects the 'thief' to be punished" in private["inner_view"]["pressures"]
        assert next(line for line in private["your_lines"] if line["issue"] == "Release")["ideal"] == (
            "Held until the landowner is satisfied"
        )


@pytest.mark.parametrize("has_hidden_interests", [False, True])
def test_public_lines_stay_available_and_scenarios_without_hidden_interests_need_no_unlock(
    content, scenario, rules, has_hidden_interests
):
    raw = content("s01_idp_camp_access")
    if not has_hidden_interests:
        raw["counterparts"][0]["hidden_interests"] = []
    raw["issues"][0]["counterpart"]["hidden"] = False
    state = start(scenario("s01_idp_camp_access"), rules).state
    private, _ = private_of(counterpart_request(config(), raw, state, []))
    assert private["your_lines"][0]["ideal"] == "Full details in advance"
    if has_hidden_interests:
        assert len(private["your_lines"]) == 1
        assert "pressures" not in private["inner_view"]
    else:
        assert len(private["your_lines"]) == len(raw["issues"])
        assert private["inner_view"]["pressures"] == raw["counterparts"][0]["constraints_from_constituency"]


def test_the_counterpart_knows_its_own_lines_authority_and_view_of_the_facts(content, scenario, rules):
    state = start(scenario("s01_idp_camp_access"), rules).state
    guidance = [rule.text for rule in rules.avatar_rules]
    request = counterpart_request(config(), content("s01_idp_camp_access"), state, [], guidance)
    private, text = private_of(request)
    assert private["authority"]["must_consult"] == ["His commanders, on distribution and escort"]
    assert "your_lines" not in private
    assert "Who are your drivers?" in private["challenges"]
    assert "never recite it" in text and '"how_to_play"' in text and "Reveal in iceberg order" in text

    state.revealed = [item["id"] for item in content("s01_idp_camp_access")["counterparts"][0]["hidden_interests"]]
    private, _ = private_of(counterpart_request(config(), content("s01_idp_camp_access"), state, [], guidance))
    distribution = next(line for line in private["your_lines"] if line["issue"] == "Who handles the distribution")
    assert distribution["red_line"] == "The militia has no visibility or role in the camp"

    checkpoint = start(scenario("s09_hostile_checkpoint"), rules).state
    private, _ = private_of(counterpart_request(config(), content("s09_hostile_checkpoint"), checkpoint, []))
    assert "A humanitarian convoy is at the checkpoint" in private["facts_and_norms"]["agreed_facts"]
    assert private["inner_view"]["implicit_position"] == ["He wants to be consulted and to be seen deciding"]


def test_the_iceberg_opens_in_the_order_the_hidden_interests_are_revealed(content, scenario, rules):
    raw = content("s01_idp_camp_access")
    hidden = [item["text"] for item in raw["counterparts"][0]["hidden_interests"]]
    state = start(scenario("s01_idp_camp_access"), rules).state
    private, text = private_of(counterpart_request(config(), raw, state, []))
    assert not any(fact in text for fact in hidden)  # unrevealed hidden-interest text never reaches the counterpart
    assert "reasoning" not in private["inner_view"] and "pressures" not in private["inner_view"]
    assert "values" not in private["inner_view"] and private["inner_view"]["reasoning_style"] == "military"
    assert private["inner_view"]["feelings"] == ["Suspicion", "Fear of being blamed"]

    state.revealed.append("loss_of_control")  # the tactical_reasoning layer
    private, _ = private_of(counterpart_request(config(), raw, state, []))
    assert private["inner_view"]["reasoning"].startswith("Whoever enters the camp")
    assert "pressures" not in private["inner_view"]
    assert "values" not in private["inner_view"]

    state.revealed.append("security_blame")  # the motive_value layer
    private, _ = private_of(counterpart_request(config(), raw, state, []))
    assert private["inner_view"]["values"] == ["Authority over the camp"]
    assert private["inner_view"]["pressures"][0] == "His commanders expect him to keep control of the camp"


def test_a_closing_line_gets_no_private_brief(content, scenario, rules):
    sc = scenario("s09_hostile_checkpoint")
    state = start(sc, rules).state
    state.dials.update(hostility=95)
    failed = step(sc, rules, state, "Enough.", Classification()).state
    text = opening(counterpart_request(config(), content("s09_hostile_checkpoint"), failed, [], ["Stay in character."]))
    assert '"private"' not in text and '"how_to_play"' not in text


def test_stakeholder_interlocutor_request(content, scenario, rules):
    raw = content("imn_detainee_access_network")
    state = start(scenario("imn_detainee_access_network"), rules).state
    sh_id = raw["stakeholders"][0]["id"]
    req = counterpart_request(config(), raw, state, [], interlocutor_id=sh_id)
    assert req.role == "counterpart"
    assert req.model == "deepseek-flash"
    assert len(req.messages) >= 1
    assert "Play the stakeholder" in req.messages[0]["content"]
    assert raw["stakeholders"][0]["role"] in req.messages[0]["content"]


def test_counterpart_request_carries_in_character_guardrail(content, scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = start(sc, rules).state
    req = counterpart_request(config(), content("s01_idp_camp_access"), state, [])
    assert "CRITICAL IN-CHARACTER SAFETY CONSTRAINT" in req.messages[0]["content"]
    assert "NEVER an AI assistant" in req.messages[0]["content"]
    assert req.max_tokens == 350


def test_multiparty_parties_see_only_their_own_channel(content, scenario, rules):
    raw = content("s08_tripartite_siege")
    state = start(scenario("s08_tripartite_siege"), rules).state
    transcript = [
        Line(role="character", text="I am Colonel Bashir, state your business.", turn=0, speaker="gov_colonel"),
        Line(role="trainee", text="Colonel, our convoy manifest is attached.", turn=1, speaker="gov_colonel"),
        Line(role="character", text="I will inspect every truck.", turn=1, speaker="gov_colonel"),
        Line(
            role="trainee", text="Commander, our secret bottom line is two trucks.", turn=2, speaker="opposition_cmdr"
        ),
        Line(role="character", text="Two trucks may pass at dawn.", turn=2, speaker="opposition_cmdr"),
        Line(role="trainee", text="And to you, Colonel: one checkpoint inspection.", turn=3),
    ]
    req = counterpart_request(config(), raw, state, transcript, interlocutor_id="gov_colonel")
    seen = [m["content"] for m in req.messages[1:]]
    assert "Commander, our secret bottom line is two trucks." not in seen
    assert "Two trucks may pass at dawn." not in seen
    assert "Colonel, our convoy manifest is attached." in seen
    assert "I will inspect every truck." in seen
    assert "And to you, Colonel: one checkpoint inspection." in seen  # the current, untagged line

    other = counterpart_request(config(), raw, state, transcript, interlocutor_id="opposition_cmdr")
    seen_other = [m["content"] for m in other.messages[1:]]
    assert "Colonel, our convoy manifest is attached." not in seen_other
    assert "Commander, our secret bottom line is two trucks." in seen_other

    stakeholder = counterpart_request(config(), raw, state, transcript, interlocutor_id=raw["stakeholders"][0]["id"])
    seen_sh = [m["content"] for m in stakeholder.messages[1:]]
    assert "Commander, our secret bottom line is two trucks." not in seen_sh
    assert "Colonel, our convoy manifest is attached." not in seen_sh
    assert "And to you, Colonel: one checkpoint inspection." in seen_sh


def test_single_party_transcript_is_unfiltered(content, scenario, rules):
    raw = content("s01_idp_camp_access")
    state = start(scenario("s01_idp_camp_access"), rules).state
    transcript = [
        Line(role="trainee", text="Good morning.", turn=1),
        Line(role="character", text="What do you want?", turn=1),
    ]
    req = counterpart_request(config(), raw, state, transcript)
    seen = [m["content"] for m in req.messages[1:]]
    assert "Good morning." in seen and "What do you want?" in seen


def test_the_request_tells_the_counterpart_who_is_who(content, scenario, rules):
    """The state's role and persona describe the counterpart itself; the person across is the humanitarian
    delegate. Without this split the model used its own rank as the trainee's vocative: reply "Captain. ..."
    to the silence nudge in session f2f911f3-2b09-4b84-a82a-9a23cd11a82b (the state's role was
    "Captain Idris Mansour", and its cultural_profile said he is addressed as "Captain")."""
    sc = scenario("detention_police_station")
    state = start(sc, rules).state
    requests = [
        counterpart_request(config(), content("detention_police_station"), state, []),
        counterpart_request(config(), content("detention_police_station"), state, [], interlocutor_id="police_captain"),
    ]
    for request in requests:
        text = opening(request)
        assert "describe YOU" in text
        assert "humanitarian delegate" in text
        assert "never by your own name, rank or title" in text
    ended_state = start(sc, rules).state
    ended_state.dials.update(hostility=95)
    ended = step(sc, rules, ended_state, "Enough.", Classification()).state
    closing = opening(counterpart_request(config(), content("detention_police_station"), ended, []))
    assert "humanitarian delegate" in closing and "describe YOU" in closing


def test_a_stakeholder_request_tells_who_is_who_and_keeps_its_authored_context(content, scenario, rules):
    raw = content("s08_tripartite_siege")
    state = start(scenario("s08_tripartite_siege"), rules).state
    state.active_interlocutor = "sheikh_khalil"
    text = opening(counterpart_request(config(), raw, state, [], interlocutor_id="sheikh_khalil"))
    assert "humanitarian delegate" in text and "describe YOU" in text
    system = json.loads(text[text.index('{"role"') :])
    assert "Preventing civilian starvation" in system["interests"]
