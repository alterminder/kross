import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, SecretStr

from nlab.llm.config import RoleConfig
from nlab.llm.openai_compat import OpenAICompatibleProvider
from nlab.llm.types import Usage, request_for
from tests.llm.fakes import FakeCompletions, bad_request, fake_client


class Answer(BaseModel):
    moves: list[str] = []


def role(**changes):
    return RoleConfig(**(dict(model="gpt-test", api_key=SecretStr("k")) | changes))


def provider_with(completions):
    return OpenAICompatibleProvider(client_factory=lambda config: fake_client(completions))


def ask(provider, config, **kwargs):
    request = request_for("classifier", config, [{"role": "user", "content": "x"}], 0)
    return asyncio.run(provider.complete(config, request, **kwargs))


def test_json_schema_is_tried_once_per_model_then_remembered():
    completions = FakeCompletions(['{"moves": []}', '{"moves": []}'])
    provider = provider_with(completions)
    first = ask(provider, role(), schema=Answer)
    ask(provider, role(), schema=Answer)
    assert [c.get("response_format", {}).get("type") for c in completions.calls] == [
        "json_schema",
        "json_object",
        "json_object",
    ]
    assert first.usage.tokens_in == 11 and first.usage.tokens_out == 4 and first.finish_reason == "stop"
    assert not first.usage.known  # a fallback attempt fired: its billing is unknown, so a hold is never released


def test_deepseek_models_skip_the_json_schema_attempt():
    completions = FakeCompletions(['{"moves": []}'])
    ask(provider_with(completions), role(model="deepseek-flash"), schema=Answer)
    assert [c.get("response_format", {}).get("type") for c in completions.calls] == ["json_object"]


def test_reasoning_effort_reaches_the_request_only_when_set():
    completions = FakeCompletions(["{}", "{}"])
    provider = provider_with(completions)
    ask(provider, role(reasoning_effort="low"), json=True)
    ask(provider, role(), json=True)
    assert completions.calls[0]["reasoning_effort"] == "low" and "reasoning_effort" not in completions.calls[1]


def test_thinking_off_wins_over_effort():
    completions = FakeCompletions(["{}"])
    ask(provider_with(completions), role(thinking=False, reasoning_effort="low"), json=True)
    call = completions.calls[0]
    assert call["extra_body"] == {"thinking": {"type": "disabled"}} and "reasoning_effort" not in call


def test_each_endpoint_gets_its_own_client():
    made = []
    provider = OpenAICompatibleProvider(client_factory=lambda config: made.append(config) or object())
    shared = role(base_url="http://main.test/v1")
    assert provider.client_for(shared) is provider.client_for(shared)
    assert provider.client_for(role(base_url="http://fast.test/v1")) is not provider.client_for(shared)
    assert len(made) == 2


def test_a_stream_yields_text_then_usage():
    completions = FakeCompletions([["Then ", "it is settled."]])
    config = role()
    request = request_for("counterpart", config, [{"role": "user", "content": "x"}], 0.7)

    async def collect():
        return [part async for part in provider_with(completions).stream(config, request)]

    assert asyncio.run(collect()) == ["Then ", "it is settled.", Usage(7, 3)]
    assert completions.calls[0]["stream"] is True


def test_the_default_client_uses_the_role_settings():
    client = OpenAICompatibleProvider().client_for(
        role(base_url="http://fast.test/v1", timeout_seconds=9, max_retries=3)
    )
    assert str(client.base_url) == "http://fast.test/v1/" and client.timeout == 9
    assert client.max_retries == 0  # hidden SDK retries are off: every paid attempt passes the budget guard


def test_the_default_client_ignores_the_ambient_openai_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ambient.invalid/v1")
    client = OpenAICompatibleProvider().client_for(role(base_url=None))
    assert str(client.base_url) == "https://api.openai.com/v1/"


def test_a_provider_without_json_modes_gets_a_plain_completion():
    class NoJson(FakeCompletions):
        async def create(self, **kwargs):
            self.calls.append(kwargs)
            if "response_format" in kwargs:
                raise bad_request()
            message = SimpleNamespace(content=self.answers.pop(0))
            return SimpleNamespace(
                choices=[SimpleNamespace(message=message, finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4),
            )

    completions = NoJson(['{"moves": []}'])
    completion = ask(provider_with(completions), role(), schema=Answer)
    assert ["response_format" in c for c in completions.calls] == [True, True, False]
    assert completion.text == '{"moves": []}'


def test_a_request_error_that_is_not_about_the_format_is_raised():
    class Broken(FakeCompletions):
        async def create(self, **kwargs):
            raise RuntimeError("network down")

    with pytest.raises(RuntimeError, match="network down"):
        ask(provider_with(Broken([])), role(), json=True)


class Reporting(FakeCompletions):
    """chat.completions that reports one raw SDK usage object: in the completion, and as the stream's usage chunk."""

    def __init__(self, usage):
        super().__init__(["{}"])
        self.usage = usage

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):

            async def chunks():
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hi"))], usage=None)
                yield SimpleNamespace(choices=[], usage=self.usage)

            return chunks()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")],
            usage=self.usage,
        )


USAGE_REPORTS = [
    pytest.param(None, (0, 0, False), id="no-usage-object"),
    pytest.param(SimpleNamespace(), (0, 0, False), id="empty-usage-object"),
    pytest.param(SimpleNamespace(prompt_tokens=11, completion_tokens=4), (11, 4, True), id="both-counts-valid"),
    pytest.param(SimpleNamespace(prompt_tokens=0, completion_tokens=0), (0, 0, True), id="explicit-zeros-are-known"),
    pytest.param(SimpleNamespace(prompt_tokens=100), (100, 0, False), id="missing-completion-count"),
    pytest.param(
        SimpleNamespace(prompt_tokens=100, completion_tokens=None), (100, 0, False), id="null-completion-count"
    ),
    pytest.param(SimpleNamespace(completion_tokens=3), (0, 3, False), id="missing-prompt-count"),
    pytest.param(SimpleNamespace(prompt_tokens=None, completion_tokens=3), (0, 3, False), id="null-prompt-count"),
    pytest.param(SimpleNamespace(prompt_tokens=None, completion_tokens=None), (0, 0, False), id="both-counts-null"),
    pytest.param(SimpleNamespace(prompt_tokens=-5, completion_tokens=3), (0, 3, False), id="negative-count"),
    pytest.param(SimpleNamespace(prompt_tokens=True, completion_tokens=3), (0, 3, False), id="boolean-count"),
    pytest.param(SimpleNamespace(prompt_tokens=1.5, completion_tokens=3), (0, 3, False), id="float-count"),
    pytest.param(SimpleNamespace(prompt_tokens="10", completion_tokens=3), (0, 3, False), id="string-count"),
]


@pytest.mark.parametrize(("raw", "expected"), USAGE_REPORTS)
def test_a_completion_reports_known_usage_only_for_valid_counts(raw, expected):
    """The SDK's usage must never silently read as a known zero (which would release a full reservation): only two
    real nonnegative integer counts settle a hold, and explicit integer zeros stay a known zero. Expected values are
    literal (tokens_in, tokens_out, known) tuples, never Usage objects built by the constructor under test."""
    usage = ask(provider_with(Reporting(raw)), role()).usage
    assert (usage.tokens_in, usage.tokens_out, usage.known) == expected


@pytest.mark.parametrize(("raw", "expected"), USAGE_REPORTS)
def test_a_stream_reports_known_usage_only_for_valid_counts(raw, expected):
    config = role()
    request = request_for("counterpart", config, [{"role": "user", "content": "x"}], 0.7)

    async def collect():
        return [part async for part in provider_with(Reporting(raw)).stream(config, request)]

    reported = [part for part in asyncio.run(collect()) if isinstance(part, Usage)]
    usage = reported[-1] if reported else None  # a stream that reports no usage yields no Usage at all
    assert ((usage.tokens_in, usage.tokens_out, usage.known) if usage else (0, 0, False)) == expected
