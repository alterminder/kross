"""The judging roles: classifier, evaluator, grant check and debrief. Each returns its checked value and a record."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from nlab.engine import Classification, Offer, Rules, State
from nlab.llm.answers import BiasCheck, ClassifierAnswer, Debrief, Evaluation, Grant, Rewritten, TurnScores
from nlab.llm.config import LLMConfig
from nlab.llm.prompts import prompt
from nlab.llm.provider import Provider
from nlab.llm.quotes import clean_classification, clean_debrief, clean_scores, quoted
from nlab.llm.structured import structured
from nlab.llm.types import Line, Message, Result, request_for


def _messages(system: str, payload: Mapping[str, Any]) -> list[Message]:
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def _lines(transcript: Sequence[Line]) -> list[dict[str, Any]]:
    return [line.model_dump() for line in transcript]


async def classify(
    provider: Provider,
    config: LLMConfig,
    content: Mapping[str, Any],
    rules: Rules,
    transcript: Sequence[Line],
    latest: str,
    offer: Offer | None = None,
) -> Result[Classification]:
    """Label ONLY the latest trainee message. `transcript` is everything before it."""
    brief = content["trainee_brief"]
    overrides = content.get("overrides") or {}
    classifier_moves = overrides.get("classifier_moves") or {}
    active_moves = {
        move_id: move.description for move_id, move in rules.moves.items() if classifier_moves.get(move_id) is not False
    }
    payload = {
        "latest": latest,
        "pending_offer": offer.label if offer else None,
        "recent_dialogue": _lines(transcript[-8:]),
        "earlier_trainee_statements": [line.text for line in transcript if line.role == "trainee"][-20:],
        "move_definitions": active_moves,
        "goal": brief["objective"],
        "mandate": brief["mandate"],
        "red_lines": brief["red_lines"],
        "issues": content.get("issues", []),
        "implementation_checklist": content.get("implementation_checklist", []),
    }
    role = config.for_role("classifier")
    request = request_for(
        "classifier", role, _messages(f"{prompt('classifier')} {prompt('classifier_level').strip()}", payload), 0
    )
    answer, record = await structured(provider, role, request, ClassifierAnswer)
    cleaned, dropped = clean_classification(answer, latest, set(active_moves))
    return Result(cleaned, record.model_copy(update={"quote_rejections": dropped}))


async def evaluate(
    provider: Provider,
    config: LLMConfig,
    content: Mapping[str, Any],
    state: State,
    transcript: Sequence[Line],
    temperature: float = 0,
    definitions: Mapping[str, Any] | None = None,
) -> Result[Evaluation]:
    """Rubric scores, each with a trainee quote, for the transcript so far. Advisory: never changes the state.
    A second opinion on the same transcript is asked at a higher `temperature`, so that it is a real second sample.
    `definitions` (Rubric.definitions) tells the evaluator what each dimension looks for and its CCHN tool."""
    rubric = content["rubric"]
    scale = rubric.get("score_scale") or {}
    scale_min = int(scale.get("min", 1))
    scale_max = int(scale.get("max", 5))
    labels = scale.get("labels")
    scale_info = ""
    if scale:
        scale_info = f" Score scale is from {scale_min} to {scale_max}."
        if labels:
            scale_info += f" Scale labels: {json.dumps(labels)}."
    payload = {
        "dimensions": rubric["dimensions"],
        **({"dimension_definitions": dict(definitions)} if definitions else {}),
        "indicators": rubric.get("indicators", []),
        "transcript": _lines(transcript),
        "trainer_injections": [item.model_dump() for item in state.injections],
        "rule_flags": [item.model_dump() for item in state.flags],
    }
    role = config.for_role("evaluator")
    request = request_for("evaluator", role, _messages(f"{prompt('evaluator')}{scale_info}", payload), temperature)
    answer, record = await structured(provider, role, request, Evaluation)
    trainee = [line.text for line in transcript if line.role == "trainee"]
    cleaned, dropped = clean_scores(answer, trainee, rubric["dimensions"], score_range=(scale_min, scale_max))
    return Result(cleaned, record.model_copy(update={"quote_rejections": dropped}))


async def grant_check(
    provider: Provider, config: LLMConfig, offered: Offer, transcript: Sequence[Line]
) -> Result[str | None]:
    """The exact granting words if the counterpart's last reply (the transcript's last line) said yes to the outcome
    on the table, else None. The engine re-checks the dials before accepting it."""
    reply = transcript[-1].text
    payload = {
        "outcome_on_the_table": offered.label,
        "outcome_kind": offered.result,
        "counterpart_last_reply": reply,
        "recent_dialogue": _lines(transcript[-6:]),
    }
    role = config.for_role("grant")
    request = request_for("grant", role, _messages(prompt("grant"), payload), 0)
    answer, record = await structured(provider, role, request, Grant)
    if not answer.granted:
        return Result(None, record)
    if not quoted(answer.quote, [reply]):
        return Result(None, record.model_copy(update={"quote_rejections": 1}))
    return Result((answer.quote or "").strip(), record)


async def rewrite_twist(
    provider: Provider, config: LLMConfig, content: Mapping[str, Any], state: State, text: str
) -> Result[str]:
    """The trainer's free text as one in-character instruction for the counterpart. The event is preserved;
    the rewrite never addresses the trainee as a trainer."""
    counterpart = content["counterparts"][0]
    payload = {
        "counterpart": counterpart["role"],
        "persona": counterpart["persona"],
        "trainer_text": text,
        "current_turn": state.turn,
    }
    role = config.for_role("director")
    request = request_for("director", role, _messages(prompt("director"), payload), 0)
    answer, record = await structured(provider, role, request, Rewritten)
    return Result(answer.instruction.strip(), record)


async def check_bias(provider: Provider, config: LLMConfig, original: str, rewritten: str) -> Result[BiasCheck]:
    """Flag unsupported stereotypes or differential treatment on protected identity in a free-text twist.
    A wrong shape fails loudly: it never passes as \"not flagged\"."""
    payload = {"trainer_text": original, "in_character_instruction": rewritten}
    role = config.for_role("bias")
    request = request_for("bias", role, _messages(prompt("bias"), payload), 0)
    answer, record = await structured(provider, role, request, BiasCheck)
    return Result(answer, record)


async def debrief(
    provider: Provider,
    config: LLMConfig,
    content: Mapping[str, Any],
    state: State,
    scores: Sequence[TurnScores],
    transcript: Sequence[Line],
) -> Result[Debrief]:
    """Summary, strengths and improvements citing turns. The outcome and scores are passed as fixed."""
    payload = {
        "outcome": state.outcome.model_dump() if state.outcome else None,
        "milestones": [item.model_dump() for item in state.reached],
        "history": _lines(transcript),
        "scores": [item.model_dump() for item in scores],
        "flags": [item.model_dump() for item in state.flags],
        "interventions": [item.model_dump() for item in state.injections],
        "focus": content["rubric"].get("indicators", []),
    }
    debrief_cfg = content.get("debrief") or {}
    feedback_style = debrief_cfg.get("feedback_style")
    style_info = f" Feedback wording style: {feedback_style}." if feedback_style else ""
    role = config.for_role("debrief")
    request = request_for(
        "debrief", role, _messages(f"{prompt('debrief')} {prompt('debrief_notes').strip()}{style_info}", payload), 0
    )
    answer, record = await structured(provider, role, request, Debrief)
    cleaned, dropped = clean_debrief(answer, transcript)
    return Result(cleaned, record.model_copy(update={"quote_rejections": dropped}))
