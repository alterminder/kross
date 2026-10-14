"""Model settings from the environment, with the hackathon's names. The app reads them once; nlab.llm never does."""

import os
from collections.abc import Mapping
from typing import Any

from dotenv import dotenv_values
from pydantic import SecretStr

from nlab.llm import LLMConfig, OpenAICompatibleProvider, Provider, RoleConfig, RoleName

PREFIXES: dict[RoleName, str] = {
    "classifier": "CLASSIFIER",
    "counterpart": "AVATAR",
    "grant": "GRANT",
    "evaluator": "EVALUATOR",
    "debrief": "DEBRIEF",
    "converter": "CONVERTER",
    "director": "DIRECTOR",
    "bias": "BIAS",
    "coach": "COACH",
    "scope": "SCOPE",
    "builder": "BUILDER",
    "illustrator": "ILLUSTRATOR",
}
OFF = {"off", "disabled", "false", "0"}


def _changes(env: Mapping[str, str], prefix: str) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if value := env.get(f"{prefix}_MODEL"):
        changes["model"] = value
    if value := env.get(f"{prefix}_API_KEY"):
        changes["api_key"] = SecretStr(value)
        # as in the hackathon: a per-role base URL applies only with a per-role key, so the main key never
        # leaves for a third-party host
        if url := env.get(f"{prefix}_BASE_URL"):
            changes["base_url"] = url
    if value := env.get(f"{prefix}_REASONING_EFFORT"):
        changes["reasoning_effort"] = value
    if (env.get(f"{prefix}_THINKING") or "").lower() in OFF:
        changes["thinking"] = False
    return changes


def llm_config_from_env(env: Mapping[str, str]) -> LLMConfig | None:
    """None when no LLM_API_KEY is set: the features that need a model then answer 503."""
    key = env.get("LLM_API_KEY")
    if not key:
        return None
    default = RoleConfig(
        model=env.get("LLM_MODEL") or "gpt-4o-mini", api_key=SecretStr(key), base_url=env.get("LLM_BASE_URL") or None
    )
    roles: dict[RoleName, RoleConfig] = {}
    for role, prefix in PREFIXES.items():
        base = roles.get("classifier", default) if role in ("grant", "scope") else default
        changes = _changes(env, prefix)
        if role == "counterpart":
            if value := env.get("AVATAR_CLOSING_EFFORT"):
                changes["closing_reasoning_effort"] = value
            if value := env.get("AVATAR_FIRST_WORD_SECONDS"):
                changes["first_word_seconds"] = float(value)
        if role == "converter":
            changes = {"timeout_seconds": 300, **changes}
        if changes or base is not default:
            roles[role] = base.model_copy(update=changes)
    return LLMConfig(default=default, roles=roles)


def default_llm() -> tuple[Provider, LLMConfig | None]:
    """The provider and settings for this process: the environment over backend/.env."""
    env = {**{k: v for k, v in dotenv_values(".env").items() if v is not None}, **os.environ}
    return OpenAICompatibleProvider(), llm_config_from_env(env)
