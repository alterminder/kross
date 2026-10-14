"""The guided scenario builder's question step: a stateless interview turn. The client sends the whole conversation
each time; the builder role decides the next question (or that nothing important is missing). The picture is a
separate, optional call (nlab.api.pictures)."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from nlab.llm.config import LLMConfig
from nlab.llm.prompts import prompt
from nlab.llm.provider import Provider
from nlab.llm.structured import record_for, structured
from nlab.llm.types import (
    AdmissionDenied,
    CallFailed,
    CallRecord,
    InputTooLarge,
    MalformedAnswer,
    Message,
    Usage,
    request_for,
)

MAX_QUESTIONS = 4  # after the 4th answered question the step is always done
MAX_QUESTION_CHARS = 2000  # BuilderIn's question limit, so the next request still fits
MAX_ANSWER_CHARS = 5000  # BuilderIn's answer limit


class BuilderReply(BaseModel):
    answer: str | None = None  # the invented answer, only when improvising
    question: str | None = None  # the next question; None when done
    done: bool = False


class Step(BaseModel):
    answer: str | None
    question: str | None
    done: bool
    records: list[CallRecord] = Field(exclude=True)  # ledger rows, read by the API layer


class BuilderFailed(RuntimeError):
    """The builder's model failed. `records` holds every attempt made, for the usage ledger."""

    def __init__(self, message: str, records: list[CallRecord]) -> None:
        super().__init__(message)
        self.records = records


def _payload(brief: str, turns: Sequence[Mapping[str, str]], question: str | None, answer: str | None) -> str:
    return json.dumps(
        {"brief": brief, "answered": list(turns), "pending_question": question, "trainer_answer": answer},
        ensure_ascii=False,
    )


async def _ask_builder(
    provider: Provider,
    config: LLMConfig,
    brief: str,
    turns: Sequence[Mapping[str, str]],
    question: str | None,
    answer: str | None,
    improvise: bool,
) -> tuple[BuilderReply, CallRecord]:
    role = config.for_role("builder")
    user = _payload(brief, turns, question, answer)
    if improvise:
        user += "\nImprovise: invent the answer to the pending question yourself."
    messages: list[Message] = [{"role": "system", "content": prompt("builder")}, {"role": "user", "content": user}]
    request = request_for("builder", role, messages, 0.3)
    started = time.monotonic()
    try:
        return await structured(provider, role, request, BuilderReply)
    except (MalformedAnswer, CallFailed) as exc:
        raise BuilderFailed("The language model did not answer", [exc.record]) from exc
    except (AdmissionDenied, InputTooLarge):
        raise  # a quota refusal is not a model failure and must keep its 429 path
    except Exception as exc:
        raise BuilderFailed(
            "The language model did not answer", [record_for(request, started, Usage(), "error", 1)]
        ) from exc


def _cap(text: str, limit: int) -> str:
    """Shorten to `limit` at a sentence or word boundary, so the next request still fits the schema."""
    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    sentence, word = cut.rfind(". "), cut.rfind(" ")
    end = sentence if sentence > 0 else word
    return (cut[: end + 1] if end > 0 else cut[:limit]).strip()


async def build_step(
    provider: Provider,
    config: LLMConfig,
    brief: str,
    turns: Sequence[Mapping[str, str]],
    question: str | None,
    answer: str | None,
    improvise: bool,
) -> Step:
    """One question step: the answer used (the trainer's, or the invented one when improvising) and the next question
    (or done). A reply with no usable question ends the interview instead of stranding it. Raises BuilderFailed when
    the model fails."""
    reply, record = await _ask_builder(provider, config, brief, turns, question, answer, improvise)
    if improvise:
        used = (reply.answer or "").strip() or None
        if used is None:
            raise BuilderFailed("The language model did not answer", [record])
        used = _cap(used, MAX_ANSWER_CHARS)
    else:
        used = answer
    answered = len(turns) + (1 if question else 0)
    next_question = _cap((reply.question or "").strip(), MAX_QUESTION_CHARS) or None
    done = reply.done or answered >= MAX_QUESTIONS or next_question is None
    return Step(answer=used, question=None if done else next_question, done=done, records=[record])
