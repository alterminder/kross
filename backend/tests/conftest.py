"""Shared fixtures: the curated content in content/ at the repository root."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from nlab.engine.models import Rubric, Rules, Scenario

CONTENT = Path(__file__).resolve().parents[2] / "content"
SCENARIO_IDS = sorted(path.stem for path in (CONTENT / "scenarios").glob("*.yaml"))


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def raw_rules() -> dict[str, Any]:
    return read_yaml(CONTENT / "behaviour_rules.yaml")  # type: ignore[no-any-return]


@pytest.fixture(scope="session")
def content() -> Callable[[str], dict[str, Any]]:
    """Raw scenario content by id. Each call returns a fresh copy, so a test may modify it."""

    def load(scenario_id: str) -> dict[str, Any]:
        return read_yaml(CONTENT / "scenarios" / f"{scenario_id}.yaml")  # type: ignore[no-any-return]

    return load


@pytest.fixture(scope="session")
def rules(raw_rules: dict[str, Any]) -> Rules:
    return Rules.model_validate(raw_rules)


@pytest.fixture(scope="session")
def rubric() -> Rubric:
    return Rubric.model_validate(read_yaml(CONTENT / "rubric.yaml"))


@pytest.fixture(scope="session")
def scenario(content: Callable[[str], dict[str, Any]]) -> Callable[[str], Scenario]:
    def load(scenario_id: str) -> Scenario:
        return Scenario.from_content(content(scenario_id))

    return load
