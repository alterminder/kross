"""Scenario validation: the bundled JSON schema first, then cross-checks against the rules and the rubric."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from itertools import islice
from typing import Any

import jsonschema
from pydantic import ValidationError

from nlab.engine.conditions import Condition, moves_in, thresholds_in
from nlab.engine.json_limits import bounded_json
from nlab.engine.models import Rubric, Rules, Scenario


@dataclass(frozen=True)
class Issue:
    """One problem, with the dotted path of the field it is about."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@cache
def scenario_schema() -> dict[str, Any]:
    """The scenario JSON schema bundled with the package (the one file the engine reads)."""
    text = files("nlab.engine").joinpath("schema/negotiation-scenario.v2.schema.json").read_text(encoding="utf-8")
    return json.loads(text)  # type: ignore[no-any-return]


def validate(content: Any, rules: Rules, rubric: Rubric) -> list[Issue]:
    """Every problem in a scenario's content; an empty list means it can be saved and played."""
    try:
        bounded_json(content, max_bytes=500_000)
    except ValueError as exc:
        return [Issue("scenario", str(exc))]
    issues = [
        Issue((".".join(map(str, error.absolute_path)) or "scenario")[:512], error.message[:512])
        for error in islice(jsonschema.Draft202012Validator(scenario_schema()).iter_errors(content), 50)
    ]
    if issues or not isinstance(content, dict):
        return issues or [Issue("scenario", "expected a mapping")]
    for index, entry in enumerate(content["outcomes"]):
        if not entry.get("when"):
            issues.append(Issue(f"outcomes.{index}.when", f"outcome {entry.get('id')}: missing condition"))
    try:
        scenario = Scenario.from_content(content)
    except ValidationError as exc:
        return issues + [Issue(".".join(map(str, error["loc"])), error["msg"]) for error in exc.errors()]
    except (KeyError, IndexError, TypeError) as exc:
        return issues + [Issue("scenario", f"missing or malformed field {exc}")]
    dials = set(scenario.counterpart.state_initial)
    party_ids = {cp.id for cp in scenario.counterparts} | {
        str(sh.get("id")) for sh in scenario.stakeholders if sh.get("id")
    }
    if scenario.multiparty:
        for index, entry in enumerate(scenario.multiparty.confidential_between):
            for pid in entry.between:
                if pid not in party_ids:
                    issues.append(
                        Issue(
                            f"multiparty.confidential_between.{index}.between",
                            f"{entry.term!r}: unknown party id {pid}",
                        )
                    )
    for index, injection in enumerate(scenario.injections):
        for dial in injection.dials:
            if dial not in dials:
                issues.append(Issue(f"injections.{index}.dials", f"injection {injection.id}: unknown dial {dial}"))
    issues.extend(_timing_issues(scenario))
    known = rubric.dimension_ids()
    for index, dimension in enumerate(scenario.rubric_dimensions):
        if dimension not in known:
            issues.append(Issue(f"rubric.dimensions.{index}", f"unknown dimension {dimension}"))
    known_dials = dials | set(rules.state_variables) | {"turn"}
    for path, condition in _conditions(scenario):
        for move in sorted(moves_in(condition) - set(rules.moves)):
            issues.append(Issue(path, f"unknown move {move}"))
        for dial in sorted(thresholds_in(condition) - known_dials):
            issues.append(Issue(path, f"unknown dial {dial}"))
    actual_dials = dials | set(rules.state_variables)
    if "overrides" in content:
        raw_overrides = content["overrides"]
        if not isinstance(raw_overrides, dict):
            issues.append(Issue("overrides", "expected a mapping"))
        else:
            if "moves" in raw_overrides:
                moves = raw_overrides["moves"]
                if not isinstance(moves, dict):
                    issues.append(Issue("overrides.moves", "expected a mapping of moves"))
                else:
                    for move_id, spec in moves.items():
                        if move_id not in rules.moves:
                            issues.append(Issue(f"overrides.moves.{move_id}", f"unknown move {move_id}"))
                            continue
                        if not isinstance(spec, dict):
                            issues.append(Issue(f"overrides.moves.{move_id}", "expected a mapping of dial deltas"))
                            continue
                        deltas = spec.get("deltas") if "deltas" in spec else spec
                        if not isinstance(deltas, dict):
                            issues.append(Issue(f"overrides.moves.{move_id}", "expected a mapping of dial deltas"))
                            continue
                        for dial, delta in deltas.items():
                            if dial not in actual_dials:
                                issues.append(Issue(f"overrides.moves.{move_id}.deltas.{dial}", f"unknown dial {dial}"))
                            elif not isinstance(delta, (int, float)) or not (-100 <= delta <= 100):
                                issues.append(
                                    Issue(f"overrides.moves.{move_id}.deltas.{dial}", f"{delta} is outside -100..100")
                                )
            if "classifier_moves" in raw_overrides:
                c_moves = raw_overrides["classifier_moves"]
                if not isinstance(c_moves, dict):
                    issues.append(Issue("overrides.classifier_moves", "expected a mapping of move toggles"))
                else:
                    for move_id, enabled in c_moves.items():
                        if move_id not in rules.moves:
                            issues.append(Issue(f"overrides.classifier_moves.{move_id}", f"unknown move {move_id}"))
                        elif not isinstance(enabled, bool):
                            issues.append(Issue(f"overrides.classifier_moves.{move_id}", "expected a boolean"))

    rubric_dict = content.get("rubric") or {}
    if "score_scale" in rubric_dict:
        scale = rubric_dict["score_scale"]
        if isinstance(scale, dict):
            s_min = scale.get("min")
            s_max = scale.get("max")
            if s_min is not None and s_max is not None and s_min >= s_max:
                issues.append(Issue("rubric.score_scale", f"min ({s_min}) must be less than max ({s_max})"))
            labels = scale.get("labels")
            if isinstance(labels, dict) and s_min is not None and s_max is not None:
                for k in labels:
                    try:
                        ik = int(k)
                        if not (s_min <= ik <= s_max):
                            issues.append(
                                Issue(
                                    f"rubric.score_scale.labels.{k}",
                                    f"label score {k} outside scale {s_min}..{s_max}",
                                )
                            )
                    except ValueError:
                        issues.append(Issue(f"rubric.score_scale.labels.{k}", f"label key {k} is not an integer"))

    reflection_dict = content.get("reflection") or {}
    if "questions" in reflection_dict and isinstance(reflection_dict["questions"], list):
        seen_q: set[str] = set()
        for idx, q in enumerate(reflection_dict["questions"]):
            if isinstance(q, dict) and "id" in q:
                qid = str(q["id"])
                if qid in seen_q:
                    issues.append(Issue(f"reflection.questions.{idx}.id", f"question id {qid} appears twice"))
                seen_q.add(qid)

    return issues[:50]


def _timing_issues(scenario: Scenario) -> list[Issue]:
    """The stages are ordered by turn: every one but the last ends on a turn later than the one before it."""
    issues: list[Issue] = []
    phases = scenario.timing.phases
    seen: set[str] = set()
    previous = 0
    for index, phase in enumerate(phases):
        path = f"timing.phases.{index}"
        if phase.id in seen:
            issues.append(Issue(f"{path}.id", f"stage {phase.id} appears twice"))
        seen.add(phase.id)
        last = index == len(phases) - 1
        if last and phase.until_turn is not None:
            issues.append(Issue(f"{path}.until_turn", "the last stage runs to the end: leave until_turn out"))
        elif not last and phase.until_turn is None:
            issues.append(
                Issue(f"{path}.until_turn", f"stage {phase.id} needs until_turn: only the last stage may omit it")
            )
        elif phase.until_turn is not None:
            if phase.until_turn <= previous:
                issues.append(Issue(f"{path}.until_turn", f"must be later than the stage before it (turn {previous})"))
            previous = max(previous, phase.until_turn)
    return issues


def _conditions(scenario: Scenario) -> Iterator[tuple[str, Condition]]:
    for index, outcome in enumerate(scenario.outcomes):
        yield f"outcomes.{index}.when", outcome.when
    for index, trigger in enumerate(scenario.triggers):
        yield f"triggers.{index}.when", trigger.when
    for index, injection in enumerate(scenario.injections):
        if injection.auto and injection.auto.when is not None:
            yield f"injections.{index}.auto.when", injection.auto.when
    for index, interest in enumerate(scenario.counterpart.hidden_interests):
        if interest.reveal_when is not None:
            yield f"counterparts.0.hidden_interests.{index}.reveal_when", interest.reveal_when
