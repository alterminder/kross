from pydantic import SecretStr

from nlab.llm.config import LLMConfig, RoleConfig
from nlab.llm.types import request_for


def role(**changes):
    return RoleConfig(**(dict(model="deepseek-flash", api_key=SecretStr("sekrit")) | changes))


def test_a_role_without_settings_uses_the_default():
    config = LLMConfig(default=role(), roles={"classifier": role(model="fast", reasoning_effort="low")})
    assert config.for_role("classifier").model == "fast"
    assert config.for_role("counterpart").model == "deepseek-flash"


def test_the_key_never_prints():
    assert "sekrit" not in repr(role().api_key) and "sekrit" not in str(role())


def test_a_request_takes_model_effort_and_thinking_from_the_role():
    request = request_for(
        "classifier", role(reasoning_effort="low", thinking=False), [{"role": "user", "content": "x"}], 0
    )
    assert (request.model, request.reasoning_effort, request.thinking, request.temperature) == (
        "deepseek-flash",
        "low",
        False,
        0,
    )
