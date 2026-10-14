"""What goes into and comes out of a model call."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nlab.llm.config import RoleConfig, RoleName

Message = dict[str, str]  # {"role": "system" | "user" | "assistant", "content": ...}


class Line(BaseModel):
    """One line of the transcript. The app keeps the transcript; the counterpart's opening line is turn 0."""

    role: Literal["trainee", "character"]
    text: str
    turn: int
    speaker: str | None = None


class Request(BaseModel):
    """Exactly what is sent for one call. Stored per turn for the counterpart, so a reviewer sees what the model got."""

    model_config = ConfigDict(frozen=True)

    role: RoleName
    model: str
    messages: list[Message]
    temperature: float
    reasoning_effort: str | None = None
    thinking: bool = True
    max_tokens: int | None = Field(default=None, gt=0)  # always bounded: request_for fills in the role's cap


def request_for(
    role: RoleName, config: RoleConfig, messages: Sequence[Message], temperature: float, max_tokens: int | None = None
) -> Request:
    return Request(
        role=role,
        model=config.model,
        messages=list(messages),
        temperature=temperature,
        reasoning_effort=config.reasoning_effort,
        thinking=config.thinking,
        max_tokens=max_tokens if max_tokens is not None else config.max_output_tokens,
    )


@dataclass(frozen=True, init=False)
class Usage:
    """What a call cost. A bare `Usage()` means the provider reported no usage at all (never the same as a known
    zero); usage is known only when both counts are real nonnegative integers (explicit integer zeros included), so a
    missing, null, negative, boolean, float or string count — or a `known=True` that carries one — leaves the usage
    unknown and the full reservation open. `reservation_ids` is provenance: every budget reservation that paid for
    the call(s) this usage aggregates."""

    tokens_in: int = 0
    tokens_out: int = 0
    known: bool = False
    reservation_ids: tuple[uuid.UUID, ...] = ()

    def __init__(
        self,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        known: bool | None = None,
        reservation_ids: tuple[uuid.UUID, ...] = (),
    ) -> None:
        counted_in = type(tokens_in) is int and tokens_in >= 0  # bool/float/str/null are not token counts
        counted_out = type(tokens_out) is int and tokens_out >= 0
        object.__setattr__(self, "tokens_in", tokens_in if counted_in else 0)
        object.__setattr__(self, "tokens_out", tokens_out if counted_out else 0)
        reported = (tokens_in is not None and tokens_out is not None) if known is None else known
        object.__setattr__(self, "known", bool(reported) and counted_in and counted_out)
        object.__setattr__(self, "reservation_ids", reservation_ids)

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.tokens_in + other.tokens_in,
            self.tokens_out + other.tokens_out,
            self.known and other.known,
            tuple(dict.fromkeys([*self.reservation_ids, *other.reservation_ids])),
        )


@dataclass(frozen=True)
class Completion:
    text: str
    finish_reason: str | None
    usage: Usage


class CallRecord(BaseModel):
    """One row of the usage ledger, minus user, org and session, which the app adds."""

    role: RoleName
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    outcome: Literal["ok", "malformed", "timeout", "error"] = "ok"
    attempts: int = 1
    reservation_ids: tuple[uuid.UUID, ...] = ()  # the budget reservations that paid: the row is analytics
    # judgements dropped by the evidence checks (missing quote, unknown id, out-of-range score, not offered/accepted)
    quote_rejections: int = 0


@dataclass(frozen=True)
class Result[T]:
    value: T
    record: CallRecord


class MalformedAnswer(RuntimeError):
    """The model answered in the wrong shape twice. Never read as "nothing observed"."""

    def __init__(self, message: str, record: CallRecord) -> None:
        super().__init__(message)
        self.record = record


class CallFailed(RuntimeError):
    """The provider failed mid-call. `record` carries the usage and attempt count accumulated so far, so a paid
    failed call is never recorded as zero."""

    def __init__(self, message: str, record: CallRecord) -> None:
        super().__init__(message)
        self.record = record


class NoAnswer(TimeoutError):
    """The counterpart's model sent no text in time, twice."""

    def __init__(self, message: str, record: CallRecord) -> None:
        super().__init__(message)
        self.record = record


class AdmissionDenied(Exception):
    """The paid call was refused before it reached the provider (no allowance left). Never a model failure:
    shared catch boundaries re-raise this instead of wrapping it into CallFailed, and no usage is charged."""


class InputTooLarge(Exception):
    """The request's bounded input estimate exceeds the role's input limit: refused before any provider call."""
