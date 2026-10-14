"""Provider for any OpenAI-compatible chat API (OpenAI, DeepSeek, Swisscom, Ollama, ...)."""

from collections.abc import AsyncIterator, Callable
from typing import Any

from openai import AsyncOpenAI, BadRequestError
from pydantic import BaseModel

from nlab.llm.config import RoleConfig
from nlab.llm.types import Completion, Request, Usage

ClientFactory = Callable[[RoleConfig], Any]


def _default_client(config: RoleConfig) -> Any:
    return AsyncOpenAI(
        api_key=config.api_key.get_secret_value(),
        base_url=config.base_url or "https://api.openai.com/v1",
        timeout=config.timeout_seconds,
        max_retries=0,  # every paid attempt must be visible to the budget guard; no hidden SDK retries
    )


def _usage(raw: Any) -> Usage:
    """Usage the provider actually reported. The `Usage` invariant decides: an absent usage object or missing,
    null or malformed counts stay unknown (never a known zero), so an understated report never clears a full
    reservation; explicit integer zeros remain a known zero."""
    return Usage(getattr(raw, "prompt_tokens", None), getattr(raw, "completion_tokens", None))


class OpenAICompatibleProvider:
    """Remembers, per instance, which models rejected `json_schema` output, and skips it for `deepseek*` models."""

    def __init__(self, client_factory: ClientFactory | None = None) -> None:
        self._factory = client_factory or _default_client
        self._clients: dict[tuple[str | None, str, float, int], Any] = {}
        self._no_json_schema: set[str] = set()

    def client_for(self, config: RoleConfig) -> Any:
        key = (config.base_url, config.api_key.get_secret_value(), config.timeout_seconds, config.max_retries)
        if key not in self._clients:
            # hidden SDK retries are disabled so every paid attempt passes the budget guard as its own call
            self._clients[key] = self._factory(config)
        return self._clients[key]

    @staticmethod
    def _options(config: RoleConfig, request: Request) -> dict[str, Any]:
        options: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            # always sent: a missing max_tokens would make the completion unbounded (0 means unlimited upstream)
            "max_tokens": request.max_tokens if request.max_tokens else config.max_output_tokens,
        }
        if not request.thinking:
            options["extra_body"] = {"thinking": {"type": "disabled"}}
        elif request.reasoning_effort:
            options["reasoning_effort"] = request.reasoning_effort
        return options

    async def complete(
        self, config: RoleConfig, request: Request, schema: type[BaseModel] | None = None, json: bool = False
    ) -> Completion:
        create = self.client_for(config).chat.completions.create
        options = self._options(config, request)
        answer = None
        total = Usage(0, 0)  # every physical attempt's usage, summed; a rejected attempt keeps the total unknown
        if (
            schema is not None
            and request.model not in self._no_json_schema
            and not request.model.startswith("deepseek")
        ):
            output = {"name": schema.__name__.lower(), "strict": True, "schema": schema.model_json_schema()}
            try:
                answer = await create(**options, response_format={"type": "json_schema", "json_schema": output})
            except BadRequestError:
                self._no_json_schema.add(request.model)
                total = total + Usage()  # a rejected request may still be billed: its usage stays unknown
        if answer is None and (schema is not None or json):
            try:
                answer = await create(**options, response_format={"type": "json_object"})
            except BadRequestError:
                answer = None
                total = total + Usage()
        if answer is None:
            answer = await create(**options)
        choice = answer.choices[0]
        return Completion(
            choice.message.content or "",
            getattr(choice, "finish_reason", None),
            total + _usage(getattr(answer, "usage", None)),
        )

    async def stream(self, config: RoleConfig, request: Request) -> AsyncIterator[str | Usage]:
        create = self.client_for(config).chat.completions.create
        options = self._options(config, request)
        fallback = False  # a fallback attempt makes the stream's billing unknown: the caller keeps its charge
        try:
            chunks = await create(**options, stream=True, stream_options={"include_usage": True})
        except BadRequestError:  # a provider that does not report usage in streams
            chunks = await create(**options, stream=True)  # a second physical attempt: its billing is unknown
            fallback = True
        try:
            async for chunk in chunks:
                choices = getattr(chunk, "choices", None)
                if choices and (text := choices[0].delta.content):
                    yield text
                if (usage := getattr(chunk, "usage", None)) is not None:
                    yield _usage(usage) if not fallback else Usage()
        finally:  # close the SDK stream even when the caller stops reading early
            close = getattr(chunks, "close", None) or getattr(chunks, "aclose", None)
            if close is not None:
                await close()
