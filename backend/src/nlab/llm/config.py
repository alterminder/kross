"""Model settings per role. The app builds them from its environment; this package never reads the environment."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

RoleName = Literal[
    "classifier",
    "counterpart",
    "grant",
    "evaluator",
    "debrief",
    "converter",
    "director",
    "bias",
    "coach",
    "scope",
    "builder",
    "illustrator",
    "painter",  # ledger only: the image model, configured through nlab.api.pictures, not a chat role
]


class RoleConfig(BaseModel):
    """Settings for one role. The openai SDK may still read OPENAI_ORG_ID / OPENAI_PROJECT_ID from the environment;
    those are deployment settings, not per-role configuration."""

    model_config = ConfigDict(frozen=True)

    model: str
    api_key: SecretStr
    base_url: str | None = None
    reasoning_effort: str | None = None
    thinking: bool = True  # False turns DeepSeek's thinking mode off; then no reasoning effort is sent
    timeout_seconds: float = Field(60, gt=0, allow_inf_nan=False)
    max_retries: int = Field(0, ge=0)  # retries inside the SDK stay off so every paid attempt passes the budget
    # guard; raising this is allowed but the guard then reserves for 1 + max_retries attempts per call
    max_output_tokens: int = Field(2048, gt=0)  # the explicit output bound for this role; requests may set a lower one
    max_input_tokens: int = Field(131_072, gt=0)  # bounded-input limit: the guard refuses larger requests
    total_deadline_seconds: float = Field(300, gt=0, allow_inf_nan=False)  # wall-clock bound, streams included
    first_word_seconds: float = Field(20, gt=0, allow_inf_nan=False)  # counterpart: a silent stream is retried once
    closing_reasoning_effort: str | None = None  # counterpart: effort for the one closing line, with thinking on


class LLMConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    default: RoleConfig
    roles: dict[RoleName, RoleConfig] = Field(default_factory=dict)

    def for_role(self, role: RoleName) -> RoleConfig:
        return self.roles.get(role, self.default)
