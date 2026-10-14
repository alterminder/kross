"""The director and bias roles for free-text trainer twists."""

import asyncio
import json

import pytest
from pydantic import SecretStr

from nlab.engine import start
from nlab.llm.answers import BiasCheck
from nlab.llm.config import LLMConfig, RoleConfig
from nlab.llm.roles import check_bias, rewrite_twist
from nlab.llm.types import MalformedAnswer
from tests.llm.fakes import FakeProvider

CONFIG = LLMConfig(default=RoleConfig(model="deepseek-flash", api_key=SecretStr("k")))


def run(awaitable):
    return asyncio.run(asyncio.wait_for(awaitable, timeout=10))


def payload(provider, index=-1):
    return json.loads(provider.requests[index].messages[1]["content"])


def test_rewrite_twist_returns_the_stripped_instruction_and_a_record(content, rules, scenario):
    provider = FakeProvider([json.dumps({"instruction": "  News arrives: a convoy was attacked nearby.  "})])
    state = start(scenario("s01_idp_camp_access"), rules).state
    result = run(
        rewrite_twist(provider, CONFIG, content("s01_idp_camp_access"), state, "  A convoy is attacked nearby  ")
    )
    assert result.value == "News arrives: a convoy was attacked nearby."
    assert result.record.role == "director" and result.record.outcome == "ok"
    sent = payload(provider)
    assert sent["trainer_text"] == "  A convoy is attacked nearby  "
    assert sent["current_turn"] == 0
    assert sent["counterpart"] and sent["persona"]  # the counterpart's role and persona, in character


def test_check_bias_returns_the_verdict_and_a_record():
    provider = FakeProvider([json.dumps({"flagged": True, "reason": "plays on an ethnic stereotype"})])
    result = run(check_bias(provider, CONFIG, "Make him furious, these people are hot-headed", "He grows furious"))
    assert result.value == BiasCheck(flagged=True, reason="plays on an ethnic stereotype")
    assert result.record.role == "bias"
    sent = payload(provider)
    assert sent["trainer_text"] == "Make him furious, these people are hot-headed"
    assert sent["in_character_instruction"] == "He grows furious"


def test_a_wrong_shape_is_retried_once_then_fails_loudly(content, rules, scenario):
    state = start(scenario("s01_idp_camp_access"), rules).state
    provider = FakeProvider(["no json here", '{"unexpected": 1}'])
    with pytest.raises(MalformedAnswer):
        run(rewrite_twist(provider, CONFIG, content("s01_idp_camp_access"), state, "text"))
    assert len(provider.requests) == 2
    # the bias check never passes as "not flagged" on a bad answer either
    provider = FakeProvider(['{"unexpected": 1}', "garbage"])
    with pytest.raises(MalformedAnswer):
        run(check_bias(provider, CONFIG, "text", "instruction"))
    assert len(provider.requests) == 2
