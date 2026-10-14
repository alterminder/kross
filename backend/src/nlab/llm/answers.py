"""What the models are asked to answer. Descriptions are part of the prompt: keep them verbatim."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Evidence(BaseModel):
    id: str
    quote: str | None = ""  # some providers send null for "no quote"


class RedLine(BaseModel):
    text: str
    quote: str | None = ""


class Violation(RedLine):
    """A red line or mandate breach the classifier reports. Only offering or accepting counts: a trainee who
    refuses it, or only mentions or asks about it, is defending the line, not crossing it."""

    action: Literal["offers", "accepts", "declines", "mentions"]


class Proposal(BaseModel):
    issue: str
    side: str
    line: str
    quote: str | None = ""


class ClassifierAnswer(BaseModel):
    moves: list[Evidence] = Field(default_factory=list)
    asked_for_goal: bool = Field(
        False,
        description=(
            "True when the LATEST trainee message asks, requests, proposes or seeks permission for the outcome "
            "described in `goal` (for example: asking to proceed, to be let through, to be allowed access), even "
            "politely, indirectly or as a question. False for greetings, introductions, answering questions, handing "
            "over documents or details, thanks, or general questions about the process."
        ),
    )
    red_lines: list[Violation] = Field(default_factory=list)
    proposals: list[Proposal] = Field(default_factory=list)
    operational_details: list[Evidence] = Field(default_factory=list)
    mandate_breaches: list[Violation] = Field(default_factory=list)
    level: Literal["political", "professional", "technical"] | None = Field(
        None,
        description=(
            "The negotiation level of the latest trainee message (CCHN Tool 4): "
            "political (who are you / why are you here, identity, values, principles), "
            "professional (how will you work, methods, operational standards), or "
            "technical (what / when / where / with whom, logistical and factual arrangements)."
        ),
    )


class Score(BaseModel):
    id: str
    score: int | None = None
    quote: str | None = ""


class Evaluation(BaseModel):
    scores: list[Score] = Field(default_factory=list)
    flags: list[RedLine] = Field(default_factory=list)


class TurnScores(Evaluation):
    """One turn's evaluation, as the app stores it and the debrief reads it."""

    turn: int


class Grant(BaseModel):
    granted: bool = Field(
        False,
        description=(
            "True only if the counterpart's LAST reply itself agrees to, allows or grants the outcome on the table: "
            "it says yes, lets the trainee or convoy proceed, or accepts the deal now. False if it only promises to "
            "check, call someone or decide later, sets a condition still to be met, asks for more information or "
            "documents, softens without agreeing, or refuses."
        ),
    )
    quote: str | None = Field(
        "", description="The exact words of the reply that grant it (copied character for character), or empty."
    )


class Rewritten(BaseModel):
    """The director's answer: the trainer's free text as one in-character instruction."""

    instruction: str

    @field_validator("instruction")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("the instruction must not be empty")
        return value


class BiasCheck(BaseModel):
    """The bias check's verdict on a free-text twist. A flagged twist is still applied; the flag is kept. Both fields
    are required: an answer without an explicit verdict is malformed, not an unflagged check."""

    flagged: bool
    reason: str


class Moment(BaseModel):
    """One turn of the debrief, with the words it is about."""

    turn: int
    note: str
    quote: str | None = Field("", description="The exact words from that turn (copied character for character).")


class MissedOpportunity(Moment):
    try_instead: str = Field("", description="One sentence the trainee could have said instead, in their own voice.")


class Focus(BaseModel):
    title: str
    advice: str


class Debrief(BaseModel):
    summary: str
    strengths: list[str]
    improvements: list[str]
    did_well: list[Moment] = Field(
        default_factory=list, description="Up to three things the trainee did well, each tied to a turn and a quote."
    )
    missed: list[MissedOpportunity] = Field(
        default_factory=list,
        description="Up to three missed opportunities, each tied to a turn and a quote, with what to try instead.",
    )
    one_focus: Focus | None = Field(
        None, description="The single behaviour with the most to gain on the next run: a short title and one advice."
    )

    @field_validator("strengths", "improvements", mode="before")
    @classmethod
    def _one_paragraph_is_a_list(cls, value: object) -> object:
        """Some providers return one paragraph instead of a list: keep it as one item."""
        return [value] if isinstance(value, str) else value


class ScopeCheck(BaseModel):
    """Whether a question to the debrief coach is about the session and negotiation practice. Required: an answer
    without a verdict is malformed, never "on topic"."""

    on_topic: bool
