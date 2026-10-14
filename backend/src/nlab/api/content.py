"""The shipped behaviour rules, rubric and curated scenarios, loaded once at start."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from nlab.engine import Rubric, Rules


class Cover(StrEnum):
    """Theme of a scenario's card. The frontend maps each key to a background image."""

    field = "field"
    camp = "camp"
    checkpoint = "checkpoint"
    detention = "detention"
    border = "border"
    school = "school"
    hospital = "hospital"
    convoy = "convoy"
    office = "office"
    custom = "custom"  # use the scenario's own painted cover (scenario_cover_images)


CURATED_COVERS: dict[str, Cover] = {
    "s01_idp_camp_access": Cover.camp,
    "s08_tripartite_siege": Cover.convoy,
    "s09_hostile_checkpoint": Cover.checkpoint,
    "detention_police_station": Cover.detention,
    "border_no_mans_land": Cover.border,
    "negotiating_safe_access_education_child": Cover.school,
    "drill_deescalation": Cover.convoy,
    "drill_level_shift": Cover.office,
    "drill_redline_pressure": Cover.convoy,
    "drill_information_quality": Cover.border,
    "drill_normative_pathway": Cover.field,
    "drill_bottomline_pause": Cover.hospital,
    "hfa_staff_labour_dispute": Cover.office,
    "fwb_guards_paid_in_kind": Cover.camp,
    "imn_detainee_access_network": Cover.detention,
    "hfe_measles_campaign_levels": Cover.hospital,
    "cacr_child_release_normative": Cover.field,
}

CONVERSION_EXAMPLE_IDS = ("s01_idp_camp_access", "s09_hostile_checkpoint")


@dataclass(frozen=True)
class Content:
    rules: Rules
    raw_rules: dict[str, Any]
    rubric: Rubric
    curated: tuple[dict[str, Any], ...]
    conversion_examples: tuple[dict[str, Any], ...]
    skills_vocabulary: tuple[str, ...]  # the fixed skills vocabulary the converter may pick from


def _plain(data: Any) -> Any:
    """YAML may hold dates and other types; the database stores JSON."""
    return json.loads(json.dumps(data, default=str))


def _read(path: Path) -> Any:
    return _plain(yaml.safe_load(path.read_text(encoding="utf-8")))


def _vocabulary(directory: Path, curated: Sequence[dict[str, Any]]) -> tuple[str, ...]:
    """The fixed skills vocabulary, built from the shipped content, never hand-typed: the curated scenarios'
    skills_tested entries. First spelling wins; deduped case-insensitively."""
    out: list[str] = []
    seen: set[str] = set()

    def add(skill: object) -> None:
        text = " ".join(str(skill).split())
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)

    for scenario in curated:
        for skill in scenario.get("skills_tested") or []:
            add(skill)
    return tuple(out)


def load_content(directory: Path) -> Content:
    raw_rules = _read(directory / "behaviour_rules.yaml")
    curated = tuple(_read(path) for path in sorted((directory / "scenarios").glob("*.yaml")))
    by_id = {scenario["id"]: scenario for scenario in curated}
    return Content(
        rules=Rules.model_validate(raw_rules),
        raw_rules=raw_rules,
        rubric=Rubric.model_validate(_read(directory / "rubric.yaml")),
        curated=curated,
        conversion_examples=tuple(by_id[scenario_id] for scenario_id in CONVERSION_EXAMPLE_IDS),
        skills_vocabulary=_vocabulary(directory, curated),
    )
