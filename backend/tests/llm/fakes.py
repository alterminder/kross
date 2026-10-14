"""Fakes for tests: a provider that answers from a script, and SDK clients shaped like openai.AsyncOpenAI."""

import asyncio
from types import SimpleNamespace

import httpx
import openai

from nlab.llm.types import Completion, Usage


class FakeProvider:
    """Answers complete() from a list of texts and stream() from a list of chunk lists. Records every request."""

    def __init__(self, answers=(), streams=()):
        self.answers, self.streams = list(answers), [list(s) for s in streams]
        self.requests, self.schemas = [], []

    async def complete(self, config, request, schema=None, json=False):
        self.requests.append(request)
        self.schemas.append(schema)
        return Completion(self.answers.pop(0), "stop", Usage(10, 5))

    async def stream(self, config, request):
        self.requests.append(request)
        for part in self.streams.pop(0):
            if part == "HANG":
                await asyncio.sleep(3600)
            yield part


def bad_request(message="response_format unavailable"):
    response = httpx.Response(400, request=httpx.Request("POST", "http://test"))
    return openai.BadRequestError(message, response=response, body=None)


class FakeCompletions:
    """chat.completions of a provider without json_schema support (like DeepSeek)."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("response_format", {}).get("type") == "json_schema":
            raise bad_request()
        if kwargs.get("stream"):
            texts = self.answers.pop(0)

            async def chunks():
                for text in texts:
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))], usage=None)
                yield SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3))

            return chunks()
        message = SimpleNamespace(content=self.answers.pop(0))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4),
        )


def fake_client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))
