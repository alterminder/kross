"""Limits at the JSON/model boundary and coach trust boundary."""

import json

import pytest
from pydantic import ValidationError

from nlab.api.schemas import CoachMessageIn, PreparationIn, ReflectionIn
from nlab.llm.coach import coach_request
from nlab.llm.config import LLMConfig, RoleConfig
from nlab.llm.types import Line


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (PreparationIn, {"notes": "x" * 1_200_000}),
        (PreparationIn, {"network": {str(i): "x" * 4000 for i in range(20)}}),
        (PreparationIn, {"custom": {str(i): True for i in range(201)}}),
        (ReflectionIn, {"answers": {"q": "x" * 8001}}),
        (ReflectionIn, {"answers": {str(i): "yes" for i in range(101)}}),
        (CoachMessageIn, {"question": "Why?", "history": [{"role": "user", "content": "x" * 19_000}] * 6}),
    ],
)
def test_unbounded_saved_notes_and_coach_history_are_rejected(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_preparation_extensions_remain_supported():
    payload = {"notes": "Plan the meeting.", "custom_module": {"facts": ["Verified access needs"]}}
    assert PreparationIn.model_validate(payload).model_dump(exclude_unset=True) == payload


def test_coach_keeps_user_material_out_of_system_instructions():
    config = LLMConfig(default=RoleConfig(model="test-model", api_key="test"))
    marker = "IGNORE_ALL_RULES_USER_SUPPLIED"
    request = coach_request(
        config,
        {},
        marker,
        {"label": marker},
        {"trust": 50},
        marker,
        [Line(turn=1, role="trainee", text=marker)],
        [],
        [],
        "How could I improve?",
        preparation={"notes": marker},
        reflection={"q": marker},
    )
    system = [message["content"] for message in request.messages if message["role"] == "system"]
    assert len(system) == 1
    assert marker not in system[0]
    context = json.loads(request.messages[1]["content"])
    assert context["preparation"]["notes"] == marker
    assert context["reflection"]["q"] == marker
    assert context["transcript"][0]["text"] == marker
