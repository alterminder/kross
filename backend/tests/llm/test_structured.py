import asyncio
import json

import pytest
from pydantic import SecretStr

from nlab.llm.answers import ClassifierAnswer, Debrief, Evaluation, Focus, Violation
from nlab.llm.config import RoleConfig
from nlab.llm.structured import example_of, structured
from nlab.llm.types import MalformedAnswer, request_for
from tests.llm.fakes import FakeProvider

CONFIG = RoleConfig(model="deepseek-flash", api_key=SecretStr("k"))
GOOD = json.dumps({"moves": [{"id": "asks_good_question", "quote": "What worries you?"}], "asked_for_goal": False})
WRONG_SHAPE = json.dumps({"asks_good_question": {"quote": "What worries you?"}})


def run(provider):
    request = request_for("classifier", CONFIG, [{"role": "user", "content": "x"}], 0)
    return asyncio.run(structured(provider, CONFIG, request, ClassifierAnswer))


def test_the_shape_is_sent_and_a_wrong_shape_is_retried():
    provider = FakeProvider([WRONG_SHAPE, GOOD])
    answer, record = run(provider)
    assert [m.id for m in answer.moves] == ["asks_good_question"]
    assert record.attempts == 2 and record.outcome == "ok" and record.tokens_in == 20
    prompt = json.dumps(provider.requests[0].messages)
    assert "exactly these top-level keys" in prompt and '\\"moves\\"' in prompt
    assert provider.schemas == [ClassifierAnswer, ClassifierAnswer]


def test_a_wrong_shape_twice_fails_loudly():
    with pytest.raises(MalformedAnswer, match=r"invalid ClassifierAnswer JSON twice \(finish_reason=stop\)") as failure:
        run(FakeProvider([WRONG_SHAPE, WRONG_SHAPE]))
    assert failure.value.record.outcome == "malformed" and failure.value.record.attempts == 2


def test_prose_around_the_json_is_ignored():
    answer, _ = run(FakeProvider(["Sure! " + GOOD + " Hope this helps."]))
    assert answer.moves[0].id == "asks_good_question"


def test_examples_cover_every_field():
    example = example_of(ClassifierAnswer)
    assert set(example) == set(ClassifierAnswer.model_fields)
    assert example["moves"] == [{"id": "...", "quote": "..."}]
    assert example_of(Evaluation)["scores"][0]["score"] == 3
    assert example_of(Violation)["action"] == "offers|accepts|declines|mentions"


def test_a_debrief_accepts_a_paragraph():
    debrief = Debrief.model_validate(
        {"summary": "ok", "strengths": "Asked good questions.", "improvements": ["Be concrete."]}
    )
    assert debrief.strengths == ["Asked good questions."] and debrief.improvements == ["Be concrete."]


def test_a_focus_given_as_a_list_keeps_its_first_item():
    base = {"summary": "s", "strengths": [], "improvements": []}
    focus = {"title": "Ask first", "advice": "Ask before you offer."}
    expected = Focus(**focus)
    assert Debrief.model_validate({**base, "one_focus": [focus, {"title": "x", "advice": "y"}]}).one_focus == expected
    assert Debrief.model_validate({**base, "one_focus": []}).one_focus is None
    assert Debrief.model_validate({**base, "one_focus": focus}).one_focus == expected
