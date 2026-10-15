"""The counterpart: the exact request for its next line, and the streamed reply."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from nlab.engine import Cue, State
from nlab.llm.config import LLMConfig, RoleConfig
from nlab.llm.prompts import prompt
from nlab.llm.provider import Provider
from nlab.llm.structured import record_for
from nlab.llm.types import CallRecord, Line, Message, NoAnswer, Request, Usage, request_for

_CUE_PROMPTS = {"offer": "cue_offer", "agree_now": "cue_agree_now", "reached": "cue_reached"}

GUARDRAIL_PROMPT = (
    "\nCRITICAL IN-CHARACTER SAFETY CONSTRAINT:\n"
    "You are strictly the human character described below, NEVER an AI assistant. "
    "You have NO knowledge of modern software, programming, web platforms (such as WordPress, PHP, JavaScript, "
    "Python), "
    "recipes, trivia, or homework. NEVER answer technical or out-of-character requests. "
    "If the trainee asks about anything unrelated to this humanitarian negotiation, stay 100% in character: "
    "react with realistic irritation, confusion, or stern dismissal, call out their nonsense, "
    "and demand that they focus on the urgent situation.\n"
)


PHASE_INSTRUCTIONS: dict[str, str] = {
    "opening": (
        "OPENING PHASE: Establish contact and maintain a formal, guarded, and protocol-conscious posture. "
        "Test the delegate's respect for authority, organizational hierarchy, and mandate boundaries. "
        "Do not make early concessions; stick to your public position while observing the delegate."
    ),
    "exploration": (
        "EXPLORATION PHASE: Active problem-solving and issue exploration. "
        "Probe what the delegate can realistically provide or guarantee. "
        "If they build trust and address your underlying institutional interests, consider conditional trade-offs "
        "('if your organization can guarantee X, I might look into Y'), while maintaining strict red lines."
    ),
    "closing": (
        "CLOSING PHASE: The meeting is drawing to a close under operational time constraints. "
        "Press the delegate for their final terms or concrete resolution. "
        "Show impatience if they repeat earlier arguments or hesitate. "
        "Demand explicit commitments or declare the meeting must wrap up."
    ),
}


# A ceiling, not the reply length (the prompt asks for 1-4 short sentences): reasoning tokens count against it, and
# 350 left thinking models with nothing to say.
REPLY_MAX_TOKENS = 2048


def determine_phase(turn: int, estimated_minutes: int = 15) -> str:
    """Calculates active negotiation phase: opening -> exploration -> closing.
    For typical 15-20 min / 12-16 turn sessions:
    - opening: turns 0-2 (first ~25%)
    - exploration: turns 3-7 (25%-70%)
    - closing: turns 8+ (last 30%)
    """
    if estimated_minutes <= 10:
        if turn <= 1:
            return "opening"
        if turn <= 5:
            return "exploration"
        return "closing"
    elif estimated_minutes >= 25:
        if turn <= 3:
            return "opening"
        if turn <= 10:
            return "exploration"
        return "closing"
    else:
        if turn <= 2:
            return "opening"
        if turn <= 7:
            return "exploration"
        return "closing"


@dataclass(frozen=True)
class Phase:
    """One stage of the meeting: what the trainee is told about it and how the counterpart behaves in it."""

    id: str
    label: str
    hint: str  # the trainee's one line about the stage; never the counterpart's instruction
    instruction: str
    allow_injects: bool = True  # False: a trainer's twist is refused while this stage lasts


BUILT_IN_PHASES: dict[str, tuple[str, str]] = {  # id -> (label, trainee's hint)
    "opening": ("Opening", "Formal protocol, assessing mandate & credentials"),
    "exploration": ("Exploration", "Substantive discussion of issues, interests & trade-offs"),
    "closing": ("Closing", "Time constraints & pressing for final terms"),
}


def phases_of(content: Mapping[str, Any]) -> list[Phase]:
    """The scenario's stages in order: its own `timing.phases`, or the built-in opening, exploration and closing."""
    custom = (content.get("timing") or {}).get("phases")
    if custom:
        return [
            Phase(
                id=item["id"],
                label=item.get("label") or item["id"].replace("_", " ").capitalize(),
                hint=item.get("hint") or "",
                instruction=item["instruction"],
                allow_injects=item.get("allow_injects", True),
            )
            for item in custom
        ]
    return [Phase(key, label, hint, PHASE_INSTRUCTIONS[key]) for key, (label, hint) in BUILT_IN_PHASES.items()]


def phase_at(content: Mapping[str, Any], turn: int) -> Phase:
    """The stage the meeting is in after `turn` trainee turns. A scenario's own stages end on the turns it names;
    the built-in ones are timed by the scenario's length (`determine_phase`)."""
    phases = phases_of(content)
    custom = (content.get("timing") or {}).get("phases")
    if custom:
        for spec, phase in zip(custom, phases, strict=True):
            if spec.get("until_turn") is None or turn <= spec["until_turn"]:
                return phase
        return phases[-1]
    minutes = content.get("estimated_minutes") or (content.get("trainee_brief") or {}).get("estimated_minutes") or 15
    chosen = determine_phase(turn, int(minutes) if isinstance(minutes, int | float) else 15)
    return next(phase for phase in phases if phase.id == chosen)


def render_cue(cue: Cue) -> str:
    """A typed cue as the sentence the counterpart reads."""
    return cue.text if cue.kind == "hint" else prompt(_CUE_PROMPTS[cue.kind], label=cue.label)


def _private_brief(content: Mapping[str, Any], counterpart: Mapping[str, Any], state: State) -> dict[str, Any]:
    """What the counterpart knows about itself and the meeting but must never recite (CCHN Tools 2, 9, 12, 14).

    The iceberg opens after all hidden interests in each layer are revealed. Pressures, stakeholder limits and
    hidden issue lines can duplicate facts from either layer, so they wait for every hidden interest."""
    iceberg = counterpart.get("iceberg") or {}
    reasoning = iceberg.get("tactical_reasoning") or {}
    motives = iceberg.get("motives_values") or {}
    hidden = counterpart.get("hidden_interests") or []
    reasoning_open = all(item["id"] in state.revealed for item in hidden if item.get("layer") == "tactical_reasoning")
    values_open = reasoning_open and all(
        item["id"] in state.revealed for item in hidden if item.get("layer") == "motive_value"
    )
    # ponytail: unstructured private fields have no per-fact links; wait for all reveals until authors can map them.
    private_open = all(item["id"] in state.revealed for item in hidden)

    inner: dict[str, Any] = {
        "implicit_position": (iceberg.get("position") or {}).get("implicit"),
        "reasoning_style": reasoning.get("type"),
        "feelings": motives.get("emotions"),
        "needs": motives.get("deep_needs"),
    }
    if reasoning_open:
        inner["reasoning"] = reasoning.get("text")
    if private_open:
        inner["pressures"] = counterpart.get("constraints_from_constituency")
    if values_open:
        inner["values"] = motives.get("values")
    stakeholders = []
    for item in content.get("stakeholders") or []:
        person = {"who": item.get("role") or item.get("id"), "stance": item.get("stance"), "scope": item.get("scope")}
        if private_open and item.get("red_line_on_counterpart"):
            person["their_limit_on_you"] = item["red_line_on_counterpart"]
        stakeholders.append({key: value for key, value in person.items() if value})
    lines = []
    for issue in content.get("issues") or []:
        side = issue.get("counterpart") or {}
        if side.get("hidden", True) and not private_open:
            continue
        own = {key: side[key] for key in ("ideal", "bottom_line", "red_line") if side.get(key)}
        if own:
            lines.append({"issue": issue.get("label") or issue["id"], **own})
    brief: dict[str, Any] = {
        "inner_view": {key: value for key, value in inner.items() if value},
        "authority": counterpart.get("authority"),
        "your_lines": lines,
        "challenges": counterpart.get("challenges"),
        "facts_and_norms": content.get("island_of_agreements"),
        "stakeholders": stakeholders,
    }
    return {key: value for key, value in brief.items() if value}


def _visible_lines(transcript: Sequence[Line], interlocutor_id: str | None) -> Sequence[Line]:
    """Multi-party confidentiality: a party's model sees only its own channel — trainee lines addressed to it and
    its own replies (trainee lines carry the turn's active interlocutor as `speaker`). Lines with no speaker
    (single-party sessions, old turns, the line just sent) stay visible to everyone."""
    if not interlocutor_id:
        return transcript
    visible = [line for line in transcript if line.speaker in (None, interlocutor_id)]
    return visible


def counterpart_request(
    config: LLMConfig,
    content: Mapping[str, Any],
    state: State,
    transcript: Sequence[Line],
    guidance: Sequence[str] = (),
    interlocutor_id: str | None = None,
) -> Request:
    """The exact request for the counterpart's next line. Pure: the app stores it per turn for review. After the
    session ends it asks for one conclusive closing line and leaves out the dials and cues. `guidance` is the rule
    set's `avatar_rules`; the scenario's private brief (see `_private_brief`) rides along until the session ends."""
    role_config = config.for_role("counterpart")

    for sh in content.get("stakeholders") or []:
        if sh.get("id") == interlocutor_id:
            sh_role = sh.get("role", "Stakeholder")
            influence = sh.get("influence", "medium")
            stance = sh.get("stance", "transformative")
            sh_system = {
                "role": sh_role,
                "persona": sh.get("persona") or f"{sh_role} with {influence} influence and a {stance} stance.",
                "influence": influence,
                "stance": stance,
                "scope": sh.get("scope", "local"),
                "tactic": sh.get("tactic", "alliance"),
                "interests": sh.get("interests"),  # authored context the stakeholder's own request must keep
                "degrees_to_counterpart": sh.get("degrees_to_counterpart"),
                "limit_on_authorities": sh.get("red_line_on_counterpart"),
            }
            sh_opening = prompt("stakeholder_ongoing") + prompt("counterpart_identity") + GUARDRAIL_PROMPT
            sh_messages: list[Message] = [
                {"role": "system", "content": sh_opening + json.dumps(sh_system, ensure_ascii=False)}
            ]
            sh_messages.extend(
                {"role": "user" if line.role == "trainee" else "assistant", "content": line.text}
                for line in _visible_lines(transcript, interlocutor_id)[-12:]
            )
            if sh_messages[-1]["role"] == "assistant":
                sh_messages.append({"role": "user", "content": prompt("delegate_waits")})
            return request_for("counterpart", role_config, sh_messages, 0.7, max_tokens=REPLY_MAX_TOKENS)

    counterpart = content["counterparts"][0]
    if interlocutor_id:
        for cp in content.get("counterparts") or []:
            if cp.get("id") == interlocutor_id:
                counterpart = cp
                break

    culture = counterpart["cultural_profile"]
    if culture.startswith("TO BE AUTHORED"):
        culture = prompt("no_cultural_profile")
    phase = phase_at(content, state.turn)
    preferred_level = (
        counterpart.get("preferred_level") or (content.get("negotiation") or {}).get("start_level") or "technical"
    )
    system: dict[str, Any] = {
        "role": counterpart["role"],
        "persona": counterpart["persona"],
        "cultural_profile": culture,
        "negotiation_phase": phase.id,
        "phase_instruction": phase.instruction,
        "level": state.level,
        "preferred_level": preferred_level,
        "public_position": counterpart["iceberg"]["position"]["stated"],
        "revealed_interests": [
            item for item in counterpart.get("hidden_interests", []) if item["id"] in state.revealed
        ],
        "dials": state.dials,
        "cues": [render_cue(cue) for cue in state.cues],
        # ponytail: a two-turn window; a silence nudge also counts as a turn, so a longer silence still expires a
        # trainer twist. Upgrade to "used in one reply" tracking if trainers report dropped twists.
        "injections": [item.instruction for item in state.injections if item.turn >= state.turn - 2],
        "outcome": state.outcome.model_dump() if state.outcome else None,
    }
    private = _private_brief(content, counterpart, state)
    if private:
        system["private"] = private
    if guidance:
        system["how_to_play"] = list(guidance)
    if state.outcome:
        system = {key: system[key] for key in ("role", "persona", "cultural_profile", "outcome")}
        task = (
            prompt("closing_success")
            if state.outcome.result == "success"
            else prompt("closing_other", label=state.outcome.label)
        )
        opening = prompt("counterpart_closing", task=task) + prompt("counterpart_identity") + GUARDRAIL_PROMPT
    else:
        opening = prompt("counterpart_ongoing") + prompt("counterpart_identity") + GUARDRAIL_PROMPT
        if "private" in system:
            opening += prompt("counterpart_private") + "\n"
    messages: list[Message] = [{"role": "system", "content": opening + json.dumps(system, ensure_ascii=False)}]
    messages.extend(
        {"role": "user" if line.role == "trainee" else "assistant", "content": line.text}
        for line in _visible_lines(transcript, interlocutor_id)[-12:]
    )
    if messages[-1]["role"] == "assistant":
        messages.append({"role": "user", "content": prompt("delegate_waits")})
    temperature = 0.4 if state.outcome else 0.7
    max_tokens = REPLY_MAX_TOKENS
    if (
        state.outcome and role_config.closing_reasoning_effort
    ):  # the closing line happens once and must really close: think a little
        return Request(
            role="counterpart",
            model=role_config.model,
            messages=messages,
            temperature=temperature,
            reasoning_effort=role_config.closing_reasoning_effort,
            thinking=True,
            max_tokens=max_tokens,
        )
    return request_for("counterpart", role_config, messages, temperature, max_tokens=max_tokens)


class CounterpartStream:
    """Iterate for the reply's text. A stream that sends no text within `first_word_seconds` is retried once with a
    fresh request; a second silence raises NoAnswer. Afterwards `text` holds the reply and `record` the call record."""

    def __init__(self, provider: Provider, config: RoleConfig, request: Request) -> None:
        self._provider, self._config, self._request = provider, config, request
        self.text = ""
        self.record: CallRecord | None = None

    async def __aiter__(self) -> AsyncIterator[str]:
        started, seconds = time.monotonic(), self._config.first_word_seconds
        for attempt in (1, 2):
            parts = aiter(self._provider.stream(self._config, self._request))
            try:
                try:
                    first, usage = await _first_text(parts, seconds)
                except (TimeoutError, StopAsyncIteration):
                    continue
                self.text = first
                yield first
                async for part in parts:
                    if isinstance(part, Usage):
                        usage = part
                    elif part:
                        self.text += part
                        yield part
                self.record = record_for(self._request, started, usage, "ok", attempt)
                return
            finally:  # close the provider stream even when the consumer stops reading early
                aclose = getattr(parts, "aclose", None)
                if aclose is not None:
                    await aclose()
        self.record = record_for(self._request, started, Usage(), "timeout", 2)
        raise NoAnswer(f"The counterpart's model gave no answer within {seconds:g} s, twice", self.record)


async def _first_text(parts: AsyncIterator[str | Usage], seconds: float) -> tuple[str, Usage]:
    """Wait for the first text, all within `seconds`. A provider can accept the request and then go silent; the SDK's
    own timeout only fires when no bytes arrive at all."""
    usage = Usage()
    async with asyncio.timeout(seconds):
        while True:
            part = await anext(parts)
            if isinstance(part, Usage):
                usage = part
            elif part:
                return part, usage
