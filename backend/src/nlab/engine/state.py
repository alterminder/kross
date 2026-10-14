"""Session state, the classifier's evidence, and the events that explain each change. All serialise to JSON."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

Result = Literal["success", "partial", "fail", "ended"]
Source = Literal["move", "rule", "reveal", "detail", "cue", "auto", "trainer", "grant", "trainee"]
EventKind = Literal["dial", "reveal", "detail", "injection", "grant", "ended", "cue", "flag", "level", "outcome"]
Quote = Annotated[str, BeforeValidator(lambda value: value or "")]  # some providers send null for "no quote"


class Outcome(BaseModel):
    id: str
    label: str
    result: Result
    turn: int


class Offer(BaseModel):
    """A success or partial outcome the counterpart has been told to put on the table."""

    id: str
    label: str
    result: Literal["success", "partial"]
    turn: int  # the turn it was first offered; a grant counts only on a later turn


class Cue(BaseModel):
    """An instruction for the counterpart's next reply. The LLM layer turns it into words."""

    kind: Literal["hint", "offer", "agree_now", "reached"]
    text: str = ""  # hint: the sentence from content
    label: str = ""  # offer, agree_now, reached: the outcome's label


class MoveRecord(BaseModel):
    turn: int
    id: str
    quote: str


class InjectionRecord(BaseModel):
    id: str
    label: str
    instruction: str
    source: Literal["auto", "trainer"]
    turn: int
    original: str | None = None  # free-text twist: what the trainer wrote
    rewritten: str | None = None  # free-text twist: the director's in-character rewrite
    bias: dict[str, Any] | None = None  # free-text twist: the bias check's verdict


class Flag(BaseModel):
    turn: int
    id: str
    quote: str
    text: str = ""


class ProposalRecord(BaseModel):
    turn: int
    issue: str
    side: str
    line: str
    quote: str


class State(BaseModel):
    """Everything the engine needs between operations. The transcript, events, scores and prompts are stored by the
    app, not here."""

    scenario_id: str
    turn: int = 0
    dials: dict[str, int]
    level: str
    goal_requested: bool = False
    offered: Offer | None = None
    outcome: Outcome | None = None
    reached: list[Outcome] = Field(default_factory=list)  # partial outcomes granted: milestones
    moves: list[MoveRecord] = Field(default_factory=list)
    injections: list[InjectionRecord] = Field(default_factory=list)
    revealed: list[str] = Field(default_factory=list)
    cues: list[Cue] = Field(default_factory=list)  # for the next reply only
    flags: list[Flag] = Field(default_factory=list)
    proposals: list[ProposalRecord] = Field(default_factory=list)
    covered_details: list[str] = Field(default_factory=list)
    active_interlocutor: str | None = None
    counterpart_dials: dict[str, dict[str, int]] = Field(default_factory=dict)
    counterpart_revealed: dict[str, list[str]] = Field(default_factory=dict)
    stakeholder_engagements: dict[str, int] = Field(default_factory=dict)


class Event(BaseModel):
    """One change and its cause. `source` keeps the hackathon log's vocabulary."""

    turn: int
    source: Source
    kind: EventKind
    dial: str | None = None
    before: int | None = None
    after: int | None = None
    ref: str | None = None  # the move, injection, hidden interest, checklist item or outcome id
    quote: str | None = None
    cue: Cue | None = None
    reason: str = ""
    text: str = ""  # flag: the red line or mandate text
    interlocutor: str | None = None


@dataclass(frozen=True)
class Step:
    """What every engine operation returns."""

    state: State
    events: tuple[Event, ...] = ()
    opening: str | None = None  # only from start(): the counterpart's first line
    openings: dict[str, str] | None = None


class _Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ItemEvidence(_Evidence):
    id: str
    quote: Quote = ""


class LineEvidence(_Evidence):
    """A red line or a must-refer item the trainee offered or accepted (the LLM layer drops the rest)."""

    text: str
    quote: Quote = ""


class ProposalEvidence(_Evidence):
    issue: str
    side: str
    line: str
    quote: Quote = ""


class Classification(_Evidence):
    """What the classifier observed in the latest trainee message. The engine re-checks every quote."""

    moves: list[ItemEvidence] = Field(default_factory=list)
    asked_for_goal: bool = False
    red_lines: list[LineEvidence] = Field(default_factory=list)
    proposals: list[ProposalEvidence] = Field(default_factory=list)
    operational_details: list[ItemEvidence] = Field(default_factory=list)
    mandate_breaches: list[LineEvidence] = Field(default_factory=list)
    level: str | None = None
