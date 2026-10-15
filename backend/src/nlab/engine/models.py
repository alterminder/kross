"""Typed views of the content: behaviour rules, rubric and scenarios.

These models are read, never written back: the raw content is what the app stores. Fields the engine does not use
are ignored here (in behaviour_rules.yaml: `status`, `state_categories`, `debrief_mode`, `debrief`, and a move's
`effect` and `flags_by_zone`). `avatar_rules` are carried for the counterpart's prompt; the engine never reads them.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainValidator, field_validator, model_validator

from nlab.engine.conditions import Condition, parse_condition, thresholds_in


def _optional_condition(raw: Any) -> Condition | None:
    # An empty or missing rule means "no rule".
    return parse_condition(raw) if raw else None


ConditionField = Annotated[Condition, PlainValidator(parse_condition)]
OptionalCondition = Annotated[Condition | None, PlainValidator(_optional_condition)]


class _Content(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class RuleOverrides(BaseModel):
    """Per move, the dial changes that replace the default ones. Only moves that differ from the default are kept."""

    model_config = ConfigDict(frozen=True)

    moves: dict[str, dict[str, int]] = Field(default_factory=dict)
    classifier_moves: dict[str, bool] = Field(default_factory=dict)


def _parse_overrides(raw: Any) -> RuleOverrides:
    if not isinstance(raw, dict):
        return RuleOverrides()
    moves = raw.get("moves")
    clean: dict[str, dict[str, int]] = {}
    if isinstance(moves, dict):
        for move_id, val in moves.items():
            if isinstance(val, dict):
                deltas = val.get("deltas") if "deltas" in val and isinstance(val["deltas"], dict) else val
                if isinstance(deltas, dict):
                    clean[str(move_id)] = {
                        str(dial): int(delta) for dial, delta in deltas.items() if isinstance(delta, (int, float))
                    }
    classifier_raw = raw.get("classifier_moves")
    clean_classifier: dict[str, bool] = {}
    if isinstance(classifier_raw, dict):
        for move_id, enabled in classifier_raw.items():
            if isinstance(enabled, bool):
                clean_classifier[str(move_id)] = enabled
    return RuleOverrides(moves=clean, classifier_moves=clean_classifier)


class Ending(_Content):
    id: str
    label: str
    result: Literal["success", "partial", "fail"]


class OutcomeRule(Ending):
    when: ConditionField


class Trigger(_Content):
    when: ConditionField
    say: str | None = None
    effect: str | None = None
    shift_level: str | None = None


class MoveRule(_Content):
    description: str
    source: str = ""
    deltas: dict[str, int] = Field(default_factory=dict)
    say_hint: str | None = None
    flag: str | None = None
    ends_session: Ending | None = None


class Consistency(_Content):
    dial: str
    recovery_per_turn: int = 0
    lowering_moves: list[str] = Field(default_factory=list)


class StateVariable(_Content):
    initial: int | None = None  # only engine-level dials (consistency) have one; the others come from the scenario


class AvatarRule(_Content):
    """One instruction for the counterpart's prompt, with the source it comes from (bank, design or a CCHN tool)."""

    text: str
    source: str = ""


class Rules(_Content):
    """behaviour_rules.yaml, possibly with an org's edits applied (see rules.effective_rules)."""

    state_variables: dict[str, StateVariable]
    moves: dict[str, MoveRule]
    consistency: Consistency | None = None
    global_outcomes: list[OutcomeRule] = Field(default_factory=list)
    global_triggers: list[Trigger] = Field(default_factory=list)
    hidden_interest_reveal_defaults: dict[str, ConditionField] = Field(default_factory=dict)
    avatar_rules: list[AvatarRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _threshold_dials_exist(self) -> Rules:
        known = set(self.state_variables) | {"turn"}
        named = (
            [(f"global_outcomes.{i}.when", o.when) for i, o in enumerate(self.global_outcomes)]
            + [(f"global_triggers.{i}.when", t.when) for i, t in enumerate(self.global_triggers)]
            + [
                (f"hidden_interest_reveal_defaults.{layer}", when)
                for layer, when in self.hidden_interest_reveal_defaults.items()
            ]
        )
        for field, condition in named:
            for dial in sorted(thresholds_in(condition) - known):
                raise ValueError(f"{field}: unknown dial {dial}")
        return self


class RubricCluster(_Content):
    label: str = ""
    dimensions: dict[str, Any]


class Rubric(_Content):
    clusters: dict[str, RubricCluster]

    def dimension_ids(self) -> set[str]:
        return {key for cluster in self.clusters.values() for key in cluster.dimensions}

    def definitions(self, ids: Collection[str]) -> dict[str, dict[str, Any]]:
        """For each named dimension the rubric knows: its label, what to look for, and the CCHN tool it comes from."""
        found: dict[str, dict[str, Any]] = {}
        for cluster in self.clusters.values():
            for key, value in cluster.dimensions.items():
                if key in ids and isinstance(value, dict):
                    found[key] = {field: value[field] for field in ("label", "look_for", "cchn") if value.get(field)}
        return found


class HiddenInterest(_Content):
    id: str
    layer: str
    text: str = ""
    reveal_when: OptionalCondition = None


class Counterpart(_Content):
    id: str = "counterpart"
    role: str = ""
    persona: str = ""
    cultural_profile: str = ""
    state_initial: dict[str, int]
    opening: str | None = None
    fallback: str | None = None  # said in place of a reply the model never gave
    stated_position: str
    hidden_interests: list[HiddenInterest] = Field(default_factory=list)


class AutoFire(_Content):
    at_turn: int | None = None
    when: OptionalCondition = None


class Injection(_Content):
    id: str
    label: str
    instruction: str
    dials: dict[str, int] = Field(default_factory=dict)
    auto: AutoFire | None = None


class PhaseSpec(_Content):
    id: str
    label: str | None = None
    hint: str | None = None
    instruction: str
    until_turn: int | None = None
    allow_injects: bool = True


class Silence(_Content):
    after_seconds: int = 90
    line: str | None = None
    penalty: int | None = None


class Timing(_Content):
    phases: list[PhaseSpec] = Field(default_factory=list)
    warnings: list[int] = Field(default_factory=list)
    on_timeout: Literal["guide", "end", "fail", "trainer"] = "guide"
    silence: Silence = Field(default_factory=Silence)


class PreparationSpec(_Content):
    time_limit_minutes: int | None = None
    modules: list[str] = Field(default_factory=list)


DEFAULT_PREPARATION_MODULES = [
    "island_of_agreements",
    "level_and_narrative",
    "lines_and_options",
]


class ScoreScale(_Content):
    min: int = 1
    max: int = 5
    labels: dict[str, str] = Field(default_factory=dict)


class DebriefConfig(_Content):
    sections: list[str] = Field(
        default_factory=lambda: [
            "agreement_check",
            "zones",
            "level_timeline",
            "iceberg_depth",
            "deescalation_report",
            "prep_vs_reality",
            "reflection",
            "competences",
        ]
    )
    feedback_style: Literal["coaching", "rigorous", "direct", "supportive"] = "coaching"


class ReflectionQuestionSpec(_Content):
    id: str
    prompt: str
    guidance: str = ""


class ReflectionConfig(_Content):
    questions: list[ReflectionQuestionSpec] = Field(default_factory=list)


class ConfidentialTerm(_Content):
    """A term the trainee must not repeat outside the parties in `between`; an empty `between` (the legacy plain
    string form) means confidential toward everyone."""

    term: str
    between: list[str] = Field(default_factory=list)


class MultipartySpec(_Content):
    confidential_between: list[ConfidentialTerm] = Field(default_factory=list)

    @field_validator("confidential_between", mode="before")
    @classmethod
    def _legacy_strings(cls, value: Any) -> Any:
        return [{"term": item} if isinstance(item, str) else item for item in value or []]


class Scenario(_Content):
    """The parts of a scenario the engine reads."""

    id: str
    counterpart: Counterpart
    counterparts: list[Counterpart] = Field(default_factory=list)
    multiparty: MultipartySpec | None = None
    outcomes: list[OutcomeRule]
    triggers: list[Trigger] = Field(default_factory=list)
    injections: list[Injection] = Field(default_factory=list)
    red_lines: list[str]
    must_refer: list[str]
    issues: list[str] = Field(default_factory=list)
    issue_tiers: dict[str, int] = Field(default_factory=dict)
    checklist: list[str] = Field(default_factory=list)
    start_level: str = "technical"
    rubric_dimensions: list[str] = Field(default_factory=list)
    score_scale: ScoreScale | None = None
    overrides: RuleOverrides = Field(default_factory=RuleOverrides)
    timing: Timing = Field(default_factory=Timing)
    preparation: PreparationSpec = Field(default_factory=PreparationSpec)
    debrief: DebriefConfig = Field(default_factory=DebriefConfig)
    reflection: ReflectionConfig = Field(default_factory=ReflectionConfig)
    degradation_cues: list[str] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    own_iceberg: dict[str, Any] = Field(default_factory=dict)
    css: dict[str, Any] = Field(default_factory=dict)
    island_of_agreements: dict[str, Any] = Field(default_factory=dict)
    stakeholders: list[dict[str, Any]] = Field(default_factory=list)

    def counterpart_for(self, interlocutor_id: str | None) -> Counterpart:
        if interlocutor_id:
            for cp in self.counterparts:
                if cp.id == interlocutor_id:
                    return cp
        return self.counterpart

    def stakeholder_for(self, interlocutor_id: str | None) -> dict[str, Any] | None:
        if interlocutor_id:
            for sh in self.stakeholders:
                if sh.get("id") == interlocutor_id:
                    return sh
        return None

    @classmethod
    def from_content(cls, content: Mapping[str, Any]) -> Scenario:
        """Build from raw scenario content. Raises pydantic.ValidationError, KeyError or IndexError on bad content;
        run validate() first to get readable problems."""
        brief = content["trainee_brief"]
        raw_cps = content["counterparts"]
        parsed_cps = [
            Counterpart.model_validate(
                {
                    **cp,
                    "id": cp.get("id") or "counterpart",
                    "role": cp.get("role") or "",
                    "persona": cp.get("persona") or "",
                    "cultural_profile": cp.get("cultural_profile") or "",
                    "stated_position": cp["iceberg"]["position"]["stated"],
                }
            )
            for cp in raw_cps
        ]
        counterpart = parsed_cps[0]
        mp_raw = content.get("multiparty")
        multiparty = MultipartySpec.model_validate(mp_raw) if isinstance(mp_raw, dict) else None
        prep_content = content.get("preparation")
        preparation: dict[str, Any]
        if prep_content is None:
            preparation = {"modules": list(DEFAULT_PREPARATION_MODULES)}
        elif isinstance(prep_content, dict):
            modules = prep_content.get("modules")
            preparation = {
                "time_limit_minutes": prep_content.get("time_limit_minutes"),
                "modules": list(DEFAULT_PREPARATION_MODULES) if modules is None else modules,
            }
        else:
            preparation = {"modules": []}

        rubric_content = content.get("rubric") or {}
        score_scale_raw = rubric_content.get("score_scale")
        score_scale = ScoreScale.model_validate(score_scale_raw) if isinstance(score_scale_raw, dict) else None

        debrief_raw = content.get("debrief")
        debrief = DebriefConfig.model_validate(debrief_raw) if isinstance(debrief_raw, dict) else DebriefConfig()

        reflection_raw = content.get("reflection")
        reflection = (
            ReflectionConfig.model_validate(reflection_raw) if isinstance(reflection_raw, dict) else ReflectionConfig()
        )

        return cls.model_validate(
            {
                "id": content["id"],
                "counterpart": counterpart,
                "counterparts": parsed_cps,
                "multiparty": multiparty,
                "outcomes": content["outcomes"],
                "triggers": content.get("triggers") or [],
                "injections": content.get("injections") or [],
                "red_lines": [item["text"] for item in brief["red_lines"]],
                "must_refer": brief["mandate"]["must_refer"],
                "issues": [item["id"] for item in content.get("issues") or []],
                "issue_tiers": {
                    item["id"]: int(item.get("tier", 1))
                    for item in content.get("issues") or []
                    if isinstance(item, dict) and "id" in item
                },
                "checklist": [item["id"] for item in content.get("implementation_checklist") or []],
                "start_level": (content.get("negotiation") or {}).get("start_level", "technical"),
                "rubric_dimensions": rubric_content.get("dimensions", []),
                "score_scale": score_scale,
                "overrides": _parse_overrides(content.get("overrides")),
                "timing": content.get("timing") or {},
                "preparation": preparation,
                "debrief": debrief,
                "reflection": reflection,
                "degradation_cues": content.get("degradation_cues") or [],
                "claims": content.get("claims") or [],
                "own_iceberg": content.get("own_iceberg") or {},
                "css": content.get("css") or {},
                "island_of_agreements": content.get("island_of_agreements") or {},
                "stakeholders": content.get("stakeholders") or [],
            }
        )
