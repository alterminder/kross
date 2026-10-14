"""Request and response bodies. The frontend's TypeScript types are generated from these via OpenAPI."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from nlab.api.content import Cover
from nlab.db.models import Mode, Role, Status, Visibility
from nlab.engine.cchn_debrief import CchnDebriefOut
from nlab.engine.json_limits import bounded_json


class ProviderOut(BaseModel):
    name: str
    label: str


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    role: Role
    personal: bool


class GuestOptionsOut(BaseModel):
    enabled: bool  # whether this deployment lets an anonymous visitor start at once


class MeOut(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str
    is_superadmin: bool
    is_guest: bool = False
    active_org: OrgOut
    orgs: list[OrgOut]


class AllowanceOut(BaseModel):
    """The caller's personal token allowance for the current UTC day. Personal only: an org's daily cap, the
    deployment's daily budget and the guests' shared budget apply independently and can still refuse a call while
    this allowance is unused. `limit_tokens` (and `remaining_percent`) is null when the personal limit is off =
    unlimited; a guest's cap is the smallest enabled of the general user and guest token caps."""

    used_tokens: int
    limit_tokens: int | None
    remaining_percent: float | None  # clamped to 0..100
    resets_at: datetime  # next 00:00 UTC


class ActiveOrgIn(BaseModel):
    org_id: uuid.UUID


class MemberOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str | None
    role: Role


class RoleIn(BaseModel):
    role: Role


class InviteIn(BaseModel):
    days: int = Field(7, ge=1, le=30)
    max_uses: int = Field(10, ge=1, le=100)


class TokenIn(BaseModel):
    """The invite token travels in the request body: URLs end up in access logs."""

    token: str = Field(max_length=100)  # real tokens are far shorter; cap the field at a sane length


class InviteOut(BaseModel):
    id: uuid.UUID
    role: Role
    expires_at: datetime
    max_uses: int
    uses: int
    url: str | None = None  # only in the response that creates it: the token is not stored


class InvitePreview(BaseModel):
    org_name: str
    role: Role
    notice: str
    problem: Literal["revoked", "expired", "used_up"] | None
    already_member: bool


class AcceptIn(BaseModel):
    token: str = Field(max_length=100)
    acknowledged: Literal[True]  # the user has read the admin-visibility notice


class AcceptOut(BaseModel):
    org_id: uuid.UUID
    org_name: str


class NewOrgIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class NewOrgOut(BaseModel):
    org_id: uuid.UUID
    name: str
    admin_invite_url: str


class DayUsageOut(BaseModel):
    day: str
    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: float


class ModelUsageOut(BaseModel):
    model: str
    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: float


class OrgUsageOut(BaseModel):
    org_id: uuid.UUID | None
    calls: int
    tokens: int
    cost_usd: float


class UsageOut(BaseModel):
    days: list[DayUsageOut]
    models: list[ModelUsageOut]
    orgs_today: list[OrgUsageOut]
    ceiling_usd: float
    spent_today_usd: float


def _capped(content: dict[str, Any]) -> dict[str, Any]:
    """Every save is an immutable version that is never deleted, so content is capped (curated ones are <100 KB)."""
    return bounded_json(content, max_bytes=500_000)  # UTF-8 bytes, not escaped Unicode


class ScenarioIn(BaseModel):
    content: dict[str, Any]
    cover: Cover | None = None  # on create, None means Cover.field; on update, None keeps the current cover

    _cap = field_validator("content")(_capped)


class ScenarioCard(BaseModel):
    id: uuid.UUID
    title: str
    cover: Cover
    cover_image_version: str | None = None  # cache-buster for the custom cover image; None: the theme cover
    visibility: Visibility
    version: int
    submitted: bool  # the owner asked the org's admins to publish it
    difficulty: str | None
    minutes: int | None
    skills: list[str]
    can_edit: bool


class ScenarioDetail(ScenarioCard):
    brief: dict[str, Any]  # the trainee brief: everything a player may see before playing
    content: dict[str, Any] | None  # the full scenario, only for someone who can edit it or review it


class ContentIn(BaseModel):
    content: dict[str, Any]

    _cap = field_validator("content")(_capped)


class IssueOut(BaseModel):
    path: str
    message: str


class VisibilityIn(BaseModel):
    visibility: Visibility


class ConvertIn(BaseModel):
    text: str = Field(max_length=200_000)
    filename: str = Field("", max_length=200)


class ConversionOut(BaseModel):
    scenario: dict[str, Any] | None
    errors: list[str]
    warnings: list[str]


class BuilderTurn(BaseModel):
    question: str = Field(max_length=2000)
    answer: str = Field(max_length=5000)


class BuilderIn(BaseModel):
    """One stateless builder step: the whole conversation, every time. Nothing is stored until the author saves."""

    brief: str = Field(max_length=20_000)
    turns: list[BuilderTurn] = Field(default_factory=list, max_length=4)  # the questions answered so far
    question: str | None = Field(None, max_length=2000)  # the pending question being answered now; None on step 1
    answer: str | None = Field(None, max_length=5000)
    improvise: bool = False


class BuilderOut(BaseModel):
    answer: str | None  # the answer used for the pending question: the user's, or the invented one
    question: str | None  # the next question; None when done
    done: bool


class PictureIn(BaseModel):
    """The painted picture of the scene so far. Decoration: it never blocks or fails the question step."""

    # 60 000 fits the maximum composed interview: a 20 000 brief plus four maximum question/answer turns
    text: str = Field(max_length=60_000)
    previous_image: str | None = Field(None, max_length=6_000_000)  # base64 PNG/JPEG/WebP, at most 4 MB decoded
    final: bool = False  # the finished scenario: edit previous_image to show the final text


class PictureOut(BaseModel):
    image: str | None  # a PNG data URL; None when pictures are off or the call failed


class MoveOut(BaseModel):
    id: str
    description: str
    source: str
    deltas: dict[str, int]
    default: dict[str, int]
    changed: bool
    ends_session: bool


class RulesOut(BaseModel):
    dials: list[str]
    moves: list[MoveOut]
    can_edit: bool


class RulesIn(BaseModel):
    moves: dict[str, dict[str, float]]


class StartIn(BaseModel):
    scenario_id: uuid.UUID
    mode: Mode = Mode.solo


class LineOut(BaseModel):
    role: Literal["trainee", "character"]
    text: str
    turn: int
    speaker: str | None = None


class CounterpartOut(BaseModel):
    id: str
    role: str = ""
    persona: str = ""
    cultural_profile: str = ""
    stated_position: str = ""

    @field_validator("role", "persona", "cultural_profile", "stated_position", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        return str(v or "")


class StakeholderOut(BaseModel):
    id: str
    role: str = ""
    persona: str = ""
    influence: str = "medium"
    stance: str = "transformative"
    scope: str = "local"

    @field_validator("role", "persona", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str:
        return str(v or "")

    @field_validator("influence", mode="before")
    @classmethod
    def _coerce_influence(cls, v: Any) -> str:
        return str(v or "medium")

    @field_validator("stance", mode="before")
    @classmethod
    def _coerce_stance(cls, v: Any) -> str:
        return str(v or "transformative")

    @field_validator("scope", mode="before")
    @classmethod
    def _coerce_scope(cls, v: Any) -> str:
        return str(v or "local")


class ConfidentialTermOut(BaseModel):
    term: str
    between: list[str] = Field(default_factory=list)


class MultipartyOut(BaseModel):
    confidential_between: list[ConfidentialTermOut] = Field(default_factory=list)


class PlayerOutcome(BaseModel):
    result: str
    label: str


class PhaseOut(BaseModel):
    id: str
    label: str
    hint: str  # what the trainee may know about the stage; never the counterpart's instruction


class PreparationIn(BaseModel):
    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def bounded_notes(cls, value: Any) -> Any:
        return bounded_json(value, max_bytes=64_000, max_depth=8, max_items=100, max_string=8000)

    skipped: bool = False
    island_of_agreements: dict[str, Any] | None = None
    information_quality: dict[str, Any] | None = None
    legitimacy_profile: dict[str, Any] | None = None
    level_and_narrative: dict[str, Any] | None = None
    counterpart_iceberg: dict[str, Any] | None = None
    common_shared_space: dict[str, Any] | None = None
    network: dict[str, Any] | None = None
    lines_and_options: dict[str, Any] | None = None
    meeting_checklist: dict[str, Any] | None = None
    notes: str | None = None


class SessionOut(BaseModel):
    """What the player sees. No dials, moves, flags, cues, reveals, scores or prompts."""

    id: uuid.UUID
    scenario_id: uuid.UUID
    title: str
    cover: str
    mode: Mode
    status: Status
    turn: int
    turn_running: bool  # the turn slot is claimed and the session is active: any claim, however old, can still
    # commit until another replaces it, and an ended session is never "running" (the finisher's claim is not a turn)
    brief: dict[str, Any]
    transcript: list[LineOut]
    outcome: PlayerOutcome | None  # only once the session has ended
    debrief_status: str | None
    phase: str | None = None
    phases: list[PhaseOut] = []  # the meeting's stages in order, for the phase bar
    minutes_total: int | None = None  # the scenario's estimated length; None when it states none
    seconds_left: int | None = None  # while active: what is left of it, counted from the session's start
    warning_minutes: list[int] = [5, 1]  # minutes left at which the clock shows a soft banner
    on_timeout: Literal["guide", "end", "fail", "trainer"] = "guide"  # what the scenario does when the minutes run out
    silence_seconds: int = 90  # how long the trainee may stay quiet before the counterpart speaks up
    preparation: dict[str, Any] | None = None
    preparation_modules: list[str] = []
    preparation_minutes: int | None = None
    reflection: dict[str, Any] | None = None
    counterparts: list[CounterpartOut] = []
    stakeholders: list[StakeholderOut] = []
    active_interlocutor: str | None = None
    multiparty: MultipartyOut | None = None


class SessionCard(BaseModel):
    id: uuid.UUID
    scenario_id: uuid.UUID
    title: str
    cover: str
    cover_image_version: str | None = None  # cache-buster when the scenario has a painted cover
    mode: Mode
    status: Status
    turn: int
    result: str | None
    player: str | None  # in an admin's org list
    player_id: uuid.UUID | None = None  # the player's user id in an admin's org list; None in "mine"
    created_at: datetime


class TurnIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    interlocutor: str | None = None


class InterlocutorIn(BaseModel):
    interlocutor: str


class InjectIn(BaseModel):
    injection_id: str


class DialIn(BaseModel):
    dial: str = Field(max_length=40)
    value: int = Field(ge=0, le=100)


class TwistIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class CommentIn(BaseModel):
    turn: int = Field(ge=0)
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class CommentOut(BaseModel):
    turn: int
    text: str
    author: str
    created_at: datetime


class OutcomeOut(BaseModel):
    """One outcome rule of the pinned version, for the watcher's goal panel."""

    id: str
    label: str
    result: str
    when: dict[str, Any]


class TurnProgress(BaseModel):
    number: int
    trainee_text: str | None
    reply_text: str | None
    dials: dict[str, int]
    events: list[dict[str, Any]]
    scores: dict[str, Any] | None
    counterpart_request: dict[str, Any] | None


class InjectionOut(BaseModel):
    id: str
    label: str


class ProgressOut(BaseModel):
    """Everything the engine knows, turn by turn: for the watching admin or the playtester."""

    session_id: uuid.UUID
    player: str
    status: Status
    title: str
    state: dict[str, Any]
    turns: list[TurnProgress]
    injections: list[InjectionOut]  # the pinned version's preset twists, for every watcher (they may steer)
    outcomes: list[OutcomeOut]  # the pinned version's outcome rules, for the goal panel
    counterpart: str  # the first counterpart's role
    comments: list[CommentOut]
    turn_running: bool
    phase: str | None = None
    phase_label: str | None = None
    injects_allowed: bool = True  # False: the current stage refuses a trainer's twist
    seconds_left: int | None = None  # of the scenario's minutes, while the session is active
    on_timeout: Literal["guide", "end", "fail", "trainer"] = "guide"


class StageOut(BaseModel):
    id: str
    label: str
    hint: str
    instruction: str  # how the counterpart behaves in it; for authors only
    allow_injects: bool


class TimingDefaultsOut(BaseModel):
    """What a scenario without its own `timing` does: the starting point the editor offers an author."""

    phases: list[StageOut]
    warnings: list[int]
    silence_after_seconds: int


class TimeDecisionIn(BaseModel):
    result: Literal["ended", "fail"]  # how the trainer ends a meeting whose time ran out


class HiddenFactOut(BaseModel):
    """One thing the counterpart was holding back, and whether the trainee drew it out."""

    id: str
    text: str
    found: bool
    unlock: str  # what would have brought it out, in words; shown only for a fact that stayed hidden


class DialCauseOut(BaseModel):
    """Why the dials moved on one turn, for the debrief: one row per cause, with the trainee's words when a move of
    theirs was the cause."""

    turn: int
    kind: Literal["move", "silence", "twist", "trainer"]
    label: str  # the move, the twist or the override, in words
    quote: str  # the trainee's words behind a move; empty for the others
    changes: dict[str, int]  # dial -> how far it actually moved (after the 0-100 limits)


class ReflectionIn(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def bounded_answers(cls, value: Any) -> Any:
        return bounded_json(value, max_bytes=64_000, max_depth=3, max_items=100, max_string=8000)


class PartyDialsOut(BaseModel):
    id: str
    role: str  # the party's role name, as session_out shows it
    dials: dict[str, int]


class DebriefOut(BaseModel):
    status: str  # pending | ready | failed | unavailable
    outcome: dict[str, Any] | None
    reached: list[dict[str, Any]]
    debrief: dict[str, Any] | None
    scores: dict[str, Any] | None  # the last scored turn's evaluation (it covers the whole transcript)
    flags: list[dict[str, Any]]
    dials: dict[str, int]
    # every engaged party's final dials, only when more than one; `dials` stays the last active party's
    counterpart_dials: list[PartyDialsOut] | None = None
    hidden_facts: list[HiddenFactOut]
    dimensions: dict[str, str]  # the scenario's rubric dimension ids and their names
    dial_causes: list[DialCauseOut]
    preparation: dict[str, Any] | None = None
    reflection: dict[str, Any] | None = None
    cchn_debrief: CchnDebriefOut | None = None
    score_scale: dict[str, Any] | None = None


class CoachMessageIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # The browser sends the chat so far. It is only data: the coach reads the latest few messages, clipped
    # (nlab.llm.coach.clean_history); this just refuses a request that is absurdly large.
    history: list[dict[str, str]] = Field(default_factory=list, max_length=60)

    @field_validator("history")
    @classmethod
    def _bounded(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        return bounded_json(value, max_bytes=64_000, max_depth=3, max_items=60, max_string=20_000)


class CoachCitationOut(BaseModel):
    id: str
    title: str
    framework: str
    citation: str
    summary: str


class CoachSuggestionsOut(BaseModel):
    suggestions: list[str]
    citations: list[CoachCitationOut]


class KnowledgeDocOut(BaseModel):
    id: str
    title: str
    framework: str
    citation: str
    tags: list[str]
    summary: str
    body_markdown: str
