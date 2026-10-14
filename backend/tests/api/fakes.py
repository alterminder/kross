"""A stand-in for Google or an org's SSO: login redirects straight to the callback with the identity in the query."""

import asyncio
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request, Response
from fastapi.responses import RedirectResponse

from nlab.api.pictures import Painting
from nlab.db.accounts import VerifiedIdentity
from nlab.llm.types import Completion, Usage


class FakeProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.label = name.title()

    async def login(self, request: Request, redirect_uri: str) -> Response:
        return RedirectResponse(f"{redirect_uri}?{request.url.query}")

    async def identity(self, request: Request) -> VerifiedIdentity:
        query = request.query_params
        return VerifiedIdentity(
            provider=self.name,
            subject=query["sub"],
            email=query.get("email") or None,
            email_verified=query.get("verified") == "1",
            name=query.get("name") or None,
        )


DEFAULT_ANSWERS = {
    "classifier": '{"moves": [], "asked_for_goal": false}',
    "grant": '{"granted": false, "quote": ""}',
    "evaluator": '{"scores": [], "flags": []}',
    "debrief": '{"summary": "A short debrief.", "strengths": ["Listened."], "improvements": ["Ask more."]}',
    "director": '{"instruction": "The situation shifts."}',
    "bias": '{"flagged": false, "reason": ""}',
    "scope": '{"on_topic": true}',
    # the guided builder: one follow-up question and an invented answer for Improvise
    "builder": json.dumps(
        {
            "answer": "The commander is Major Deng; he wants a written request from the NGO headquarters "
            "before he lets anyone through.",
            "question": "What is at stake if the trucks are delayed, and how much time do you have?",
            "done": False,
        }
    ),
    # the illustrator: one scene for the painter
    "illustrator": json.dumps(
        {"scene": "A dusty roadside checkpoint: a lowered barrier, a small hut, two white trucks waiting in a line."}
    ),
}

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-painting"
JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg"


@dataclass
class FakePainter:
    """An image painter that never touches the network. `fail` makes every call blow up."""

    model: str = "fake-image"
    fail: bool = False
    prompts: list[str] = field(default_factory=list)  # every prompt painted
    previous: list[bytes | None] = field(default_factory=list)  # the edit input of every call, if any
    mimes: list[str] = field(default_factory=list)  # the claimed type of every edit input

    @property
    def available(self) -> bool:
        return True

    async def paint(self, text: str, previous: bytes | None = None, previous_mime: str = "image/png") -> Painting:
        self.prompts.append(text)
        self.previous.append(previous)
        self.mimes.append(previous_mime)
        if self.fail:
            raise ConnectionError("painter unreachable")
        return Painting(image=PNG, mime="image/png", tokens_in=5, tokens_out=7)


class ScriptedModel:
    """A provider that answers by role. `answers[role]` is a queue of texts (or exceptions to raise); an empty queue
    falls back to DEFAULT_ANSWERS. `replies` is a queue of counterpart streams (a "HANG" part never answers, an
    exception part raises). `calls` counts calls per role. `entered[role]` fires when a call arrives, `gates[role]`
    blocks that role until the test opens it, `once[role]` gates only that role's next call, and a role in `hang`
    never answers."""

    def __init__(self) -> None:
        self.answers: defaultdict[str, list[object]] = defaultdict(list)
        self.replies: list[list[object]] = []
        self.calls: Counter[str] = Counter()
        self.requests: list[Any] = []
        self.entered: defaultdict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.gates: dict[str, asyncio.Event] = {}
        self.once: dict[str, asyncio.Event] = {}
        self.hang: set[str] = set()

    async def complete(self, config, request, schema=None, json=False):
        self.calls[request.role] += 1
        self.requests.append(request)
        self.entered[request.role].set()
        gate = self.once.pop(request.role, None)
        if gate is not None:
            await gate.wait()
        if request.role in self.gates:
            await self.gates[request.role].wait()
        if request.role in self.hang:
            await asyncio.sleep(3600)
        queue = self.answers[request.role]
        answer = queue.pop(0) if queue else DEFAULT_ANSWERS[request.role]
        if isinstance(answer, BaseException):
            raise answer
        return Completion(str(answer), "stop", Usage(10, 5))

    async def stream(self, config, request):
        role = request.role
        self.calls[role] += 1
        self.requests.append(request)
        self.entered[role].set()
        if role in self.gates:
            await self.gates[role].wait()
        default_reply = (
            [
                "Under CCHN Tool 9 (Analyzing the Position of the Counterpart), you stayed on his stated position. ",
                "Try instead asking how he reached it and who he answers to.",
            ]
            if role == "coach"
            else ["I hear you. ", "Go on."]
        )
        parts = self.replies.pop(0) if self.replies else default_reply
        for part in parts:
            if isinstance(part, BaseException):
                raise part
            if part == "HANG":
                await asyncio.sleep(3600)
            yield part
