import asyncio
import json

from pydantic import SecretStr

from nlab.engine import Offer, start
from nlab.llm.answers import TurnScores
from nlab.llm.config import LLMConfig, RoleConfig
from nlab.llm.roles import classify, debrief, evaluate, grant_check
from nlab.llm.types import Line
from tests.llm.fakes import FakeProvider

CONFIG = LLMConfig(default=RoleConfig(model="deepseek-flash", api_key=SecretStr("k")))
MSG = "I hear your concern. What worries your commanders most?"
GOOD = json.dumps({"moves": [{"id": "asks_good_question", "quote": "What worries your commanders most?"}]})
OFFER = Offer(id="passage", label="Convoy passage agreed", result="success", turn=1)


def payload(provider, index=-1):
    return json.loads(provider.requests[index].messages[1]["content"])


def test_classify_returns_checked_moves_and_a_record(content, rules):
    provider = FakeProvider([GOOD])
    result = asyncio.run(classify(provider, CONFIG, content("s01_idp_camp_access"), rules, [], MSG))
    assert [m.id for m in result.value.moves] == ["asks_good_question"]
    assert result.record.role == "classifier" and result.record.quote_rejections == 0
    assert provider.requests[0].temperature == 0


def test_the_classifier_sees_earlier_statements(content, rules):
    provider = FakeProvider([json.dumps({"moves": []})])
    transcript = [
        Line(role="character", text="Hello", turn=0),
        Line(role="trainee", text="We saw the arrest at the crossroads.", turn=1),
    ]
    asyncio.run(classify(provider, CONFIG, content("s01_idp_camp_access"), rules, transcript, "Nobody saw anything."))
    assert payload(provider)["earlier_trainee_statements"] == ["We saw the arrest at the crossroads."]


def test_a_pending_offer_reaches_the_classifier(content, rules):
    provider = FakeProvider([GOOD])
    asyncio.run(classify(provider, CONFIG, content("s09_hostile_checkpoint"), rules, [], "Yes, agreed.", OFFER))
    assert payload(provider)["pending_offer"] == "Convoy passage agreed"
    assert "accept, confirm or ask for that offer" in provider.requests[0].messages[0]["content"]


def test_a_grant_needs_the_model_to_say_so_and_quote_the_reply_exactly():
    transcript = [
        Line(role="character", text="Papers are in order. You may pass, and tell the capital I was informed.", turn=1)
    ]
    said = asyncio.run(
        grant_check(FakeProvider([json.dumps({"granted": True, "quote": "You may pass"})]), CONFIG, OFFER, transcript)
    )
    assert said.value == "You may pass" and said.record.role == "grant"
    invented = asyncio.run(
        grant_check(
            FakeProvider([json.dumps({"granted": True, "quote": "Your convoy is free to leave"})]),
            CONFIG,
            OFFER,
            transcript,
        )
    )
    assert invented.value is None and invented.record.quote_rejections == 1
    refused = asyncio.run(
        grant_check(FakeProvider([json.dumps({"granted": False, "quote": "You may pass"})]), CONFIG, OFFER, transcript)
    )
    assert refused.value is None


def test_evaluate_scores_only_quoted_rubric_dimensions(content, scenario, rules):
    sc = scenario("s01_idp_camp_access")
    state = start(sc, rules).state
    transcript = [Line(role="trainee", text="What worries you?", turn=1)]
    answer = json.dumps(
        {
            "scores": [
                {"id": "questioning", "score": 4, "quote": "What worries you?"},
                {"id": "trust_building", "score": 5, "quote": "nothing like it"},
            ]
        }
    )
    provider = FakeProvider([answer])
    result = asyncio.run(evaluate(provider, CONFIG, content("s01_idp_camp_access"), state, transcript))
    assert {s.id: s.score for s in result.value.scores} == {"questioning": 4, "trust_building": None}
    assert result.record.quote_rejections == 1
    assert payload(provider)["dimensions"] == content("s01_idp_camp_access")["rubric"]["dimensions"]
    assert "dimension_definitions" not in payload(provider)


def test_evaluate_reads_what_each_dimension_looks_for(content, scenario, rules, rubric):
    raw = content("s01_idp_camp_access")
    state = start(scenario("s01_idp_camp_access"), rules).state
    provider = FakeProvider([json.dumps({"scores": []})])
    definitions = rubric.definitions(raw["rubric"]["dimensions"])
    lines = [Line(role="trainee", text="Hello.", turn=1)]
    asyncio.run(evaluate(provider, CONFIG, raw, state, lines, definitions=definitions))
    sent = payload(provider)["dimension_definitions"]
    assert set(sent) == set(raw["rubric"]["dimensions"]) & rubric.dimension_ids()
    assert sent["questioning"]["cchn"] == "T6, T9"
    assert "Follows the order what (position) -> how (reasoning) -> why (motives)" in sent["questioning"]["look_for"]


def test_debrief_gets_the_fixed_outcome_and_scores(content, scenario, rules):
    from nlab.engine import end

    sc = scenario("s01_idp_camp_access")
    state = end(start(sc, rules).state).state
    provider = FakeProvider([json.dumps({"summary": "Stopped early.", "strengths": [], "improvements": ["Ask more."]})])
    scores = [TurnScores(turn=1, scores=[], flags=[])]
    result = asyncio.run(debrief(provider, CONFIG, content("s01_idp_camp_access"), state, scores, []))
    assert result.value.summary == "Stopped early."
    sent = payload(provider)
    assert sent["outcome"]["result"] == "ended" and sent["scores"] == [{"scores": [], "flags": [], "turn": 1}]
