"""Ask for JSON, validate it, retry once, and fail loudly."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from nlab.llm.config import RoleConfig
from nlab.llm.prompts import prompt
from nlab.llm.provider import Provider
from nlab.llm.types import (
    AdmissionDenied,
    CallFailed,
    CallRecord,
    InputTooLarge,
    MalformedAnswer,
    Message,
    Request,
    Usage,
)


def example_of(model: type[BaseModel]) -> dict[str, Any]:
    """A filled-in JSON example of a model, so any model can copy the exact shape."""
    out: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        annotation = field.annotation
        args = getattr(annotation, "__args__", ())
        item = args[0] if args else None
        if isinstance(item, type) and issubclass(item, BaseModel):
            out[name] = [example_of(item)]
        elif getattr(annotation, "__origin__", None) is Literal:
            out[name] = "|".join(args)
        elif annotation is bool:
            out[name] = False
        elif annotation is int or int in args:
            out[name] = 3
        elif annotation is str or str in args:
            out[name] = "..."
        elif getattr(annotation, "__origin__", None) is list:
            out[name] = ["..."]
        else:
            out[name] = None
    return out


def shape_message(schema: type[BaseModel]) -> Message:
    return {"role": "system", "content": prompt("shape_intro") + json.dumps(example_of(schema), ensure_ascii=False)}


def record_for(
    request: Request,
    started: float,
    usage: Usage,
    outcome: Literal["ok", "malformed", "timeout", "error"],
    attempts: int,
) -> CallRecord:
    return CallRecord(
        role=request.role,
        model=request.model,
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        latency_ms=round((time.monotonic() - started) * 1000),
        outcome=outcome,
        attempts=attempts,
        reservation_ids=usage.reservation_ids,
    )


async def structured[T: BaseModel](
    provider: Provider, config: RoleConfig, request: Request, schema: type[T]
) -> tuple[T, CallRecord]:
    """The model's answer as `schema`. An answer that uses none of the expected keys counts as malformed, so a wrong
    shape fails instead of validating as "nothing observed". Raises MalformedAnswer after two bad answers."""
    messages: Sequence[Message] = [*request.messages, shape_message(schema)]
    started, usage = time.monotonic(), Usage()
    for attempt in (1, 2):
        try:
            completion = await provider.complete(
                config, request.model_copy(update={"messages": list(messages)}), schema=schema
            )
        except (AdmissionDenied, InputTooLarge):
            raise  # a quota refusal is not a model failure and must keep its 429 path
        except Exception as exc:  # a transport failure carries the usage and attempts paid so far
            raise CallFailed(
                str(exc) or type(exc).__name__, record_for(request, started, usage, "error", attempt)
            ) from exc
        usage += completion.usage
        content = completion.text
        try:
            data = json.loads(content[content.index("{") : content.rindex("}") + 1])
            if not isinstance(data, dict) or not set(data) & set(schema.model_fields):
                raise ValueError("answer does not use the expected keys")
            return schema.model_validate(data), record_for(request, started, usage, "ok", attempt)
        except (ValueError, ValidationError) as exc:
            if attempt == 2:
                record = record_for(request, started, usage, "malformed", attempt)
                raise MalformedAnswer(f"Model returned invalid {schema.__name__} JSON twice", record) from exc
            messages = [
                *messages,
                {"role": "assistant", "content": content},
                {"role": "user", "content": prompt("retry_json")},
            ]
    raise AssertionError("unreachable")
