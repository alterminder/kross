"""The rules engine: trainee turns, grants, twists and endings (behaviour ported from the hackathon prototype).

Pure: inputs are never modified, and nothing here calls a model, reads a file or touches the environment. Every
function returns a Step: the new state and the events that explain each change.
"""

from __future__ import annotations

from typing import Any, Literal

from nlab.engine.conditions import NEVER, ProposalLine, matches, without_goal
from nlab.engine.errors import EngineError
from nlab.engine.models import Injection, Rules, Scenario
from nlab.engine.state import (
    Classification,
    Cue,
    Event,
    EventKind,
    Flag,
    InjectionRecord,
    MoveRecord,
    Offer,
    Outcome,
    ProposalRecord,
    Source,
    State,
    Step,
)

TwistSource = Literal["auto", "trainer"]


class _Change:
    """A private copy of the state, and the events of one operation."""

    def __init__(self, state: State) -> None:
        self.state = state.model_copy(deep=True)
        self.events: list[Event] = []

    def add(self, source: Source, kind: EventKind, **fields: Any) -> None:
        self.events.append(Event(turn=self.state.turn, source=source, kind=kind, **fields))

    def dial(
        self,
        dial: str,
        delta: int,
        source: Source,
        *,
        interlocutor: str | None = None,
        ref: str | None = None,
        quote: str | None = None,
        reason: str = "",
    ) -> None:
        target_id = interlocutor or self.state.active_interlocutor
        if target_id and target_id in self.state.counterpart_dials:
            dials = self.state.counterpart_dials[target_id]
        else:
            dials = self.state.dials
        if dial not in dials:  # a state saved before this dial existed
            return
        before = dials[dial]
        after = max(0, min(100, before + delta))
        dials[dial] = after
        if not target_id or target_id == self.state.active_interlocutor:
            self.state.dials[dial] = after
        self.add(
            source,
            "dial",
            dial=dial,
            before=before,
            after=after,
            interlocutor=target_id,
            ref=ref,
            quote=quote,
            reason=reason,
        )

    def done(self) -> Step:
        return Step(self.state, tuple(self.events))


def start(scenario: Scenario, rules: Rules) -> Step:
    """A new session: the scenario's dials plus engine-level ones (consistency), and the counterpart's first line."""
    cps = scenario.counterparts if scenario.counterparts else [scenario.counterpart]
    primary_cp = cps[0]

    counterpart_dials: dict[str, dict[str, int]] = {}
    counterpart_revealed: dict[str, list[str]] = {}
    openings: dict[str, str] = {}

    for cp in cps:
        cp_dials = dict(cp.state_initial)
        for name, variable in rules.state_variables.items():
            if variable.initial is not None:
                cp_dials.setdefault(name, variable.initial)
        counterpart_dials[cp.id] = cp_dials
        counterpart_revealed[cp.id] = []
        openings[cp.id] = cp.opening or cp.stated_position

    initial_dials = dict(counterpart_dials[primary_cp.id])
    for sh in scenario.stakeholders:  # stakeholders keep their own dials too, seeded from the scenario baseline
        if sh_id := sh.get("id"):
            counterpart_dials.setdefault(sh_id, dict(initial_dials))
    state = State(
        scenario_id=scenario.id,
        dials=initial_dials,
        level=scenario.start_level,
        # always the speaking party (even single-party): the opening line is stored with this state as its
        # speaker, and a transcript line with no speaker cannot be named in the dialogue
        active_interlocutor=primary_cp.id,
        counterpart_dials=counterpart_dials,
        counterpart_revealed=counterpart_revealed,
        stakeholder_engagements={},
    )
    return Step(state, (), primary_cp.opening or primary_cp.stated_position, openings=openings)


CONSTRUCTIVE_STAKEHOLDER_MOVES = {
    "identifies_interest",
    "translates_principle",
    "frames_shared_benefit",
    "asks_about_constituency",
    "acknowledges_emotion",
    "reframes_core_issue",
    "explores_interests",
    "proposes_compromise",
    "offers_options",
}


def step(
    scenario: Scenario,
    rules: Rules,
    state: State,
    text: str,
    classification: Classification,
    interlocutor: str | None = None,
) -> Step:
    """One trainee turn, in a fixed order: evidence, moves, consistency, red lines, mandate, triggers, reveals,
    automatic twists, fail outcomes, then an offer if a success or partial outcome is in range."""
    if state.outcome:
        raise EngineError("The session has ended")
    text = text.strip()
    if not text:
        raise EngineError("Message is empty")
    target_id = (
        interlocutor
        or state.active_interlocutor
        or (scenario.counterparts[0].id if scenario.counterparts else "counterpart")
    )
    change = _Change(state)
    current = change.state
    current.turn += 1
    current.goal_requested = classification.asked_for_goal
    current.cues = []
    current.offered = None  # recomputed at the end of the step
    active_prev = state.active_interlocutor or (scenario.counterparts[0].id if scenario.counterparts else None)
    if not current.counterpart_dials:
        current.counterpart_dials = {target_id: dict(state.dials)}
    elif active_prev and active_prev in current.counterpart_dials:
        current.counterpart_dials[active_prev] = dict(state.dials)
    if scenario.stakeholder_for(target_id) and target_id not in current.counterpart_dials:
        # a session started before stakeholders had their own dials: seed from the current ones
        current.counterpart_dials[target_id] = dict(state.dials)

    current.active_interlocutor = target_id  # every turn names its speaker, single-party included
    if target_id in current.counterpart_dials:
        current.dials = current.counterpart_dials[target_id]

    folded = text.casefold()

    def quoted(quote: str) -> bool:
        return bool(quote) and quote.casefold() in folded

    moves: set[str] = set()

    # Multi-party confidentiality breach check (CCHN Tool 14)
    if scenario.multiparty and scenario.multiparty.confidential_between:
        for entry in scenario.multiparty.confidential_between:
            # object form: a breach only when the target is outside the parties the term is confidential between
            if entry.between and target_id in entry.between:
                continue
            if entry.term.casefold() in folded:
                current.flags.append(Flag(turn=current.turn, id="confidentiality_breach", quote=entry.term))
                targets = (
                    [cp.id for cp in scenario.counterparts] if scenario.stakeholder_for(target_id) else [target_id]
                )
                for tid in targets:
                    change.dial(
                        "hostility",
                        25,
                        "rule",
                        interlocutor=tid,
                        ref="confidentiality_breach",
                        reason="Breach of multi-party confidentiality",
                    )
                change.add(
                    "rule",
                    "flag",
                    ref="confidentiality_breach",
                    quote=entry.term,
                    interlocutor=target_id,
                    reason="Confidentiality breach between parties",
                )
                current.cues.append(
                    Cue(
                        kind="hint",
                        text="You disclosed confidential information! Counterpart hostility has surged.",
                    )
                )
                break

    # Network Play: Stakeholder engagement (CCHN Tool 12) — the shared move/red-line/mandate handling below
    # also runs for stakeholder turns; only the engagement count and the network-influence effect stay specific.
    sh = scenario.stakeholder_for(target_id)
    if sh:
        current.stakeholder_engagements[target_id] = current.stakeholder_engagements.get(target_id, 0) + 1
        change.add(
            "trainee",
            "detail",
            ref=f"stakeholder:{target_id}",
            interlocutor=target_id,
            reason=f"Engaged stakeholder {sh.get('role')}",
        )

    proposals: list[ProposalLine] = []
    issues = set(scenario.issues)
    for proposal in classification.proposals:
        if (
            proposal.issue in issues
            and proposal.side in ("own", "counterpart")
            and proposal.line in ("bottom_line", "red_line")
            and quoted(proposal.quote)
        ):
            proposals.append(ProposalLine(proposal.issue, proposal.side, proposal.line))
            current.proposals.append(
                ProposalRecord(
                    turn=current.turn,
                    issue=proposal.issue,
                    side=proposal.side,
                    line=proposal.line,
                    quote=proposal.quote,
                )
            )
    details = set(scenario.checklist)
    for detail in classification.operational_details:
        if detail.id in details and quoted(detail.quote):
            if detail.id not in current.covered_details:
                current.covered_details.append(detail.id)
            change.add("detail", "detail", ref=detail.id, quote=detail.quote, interlocutor=target_id)
    if classification.level and classification.level != current.level:
        current.level = classification.level
        change.add("trainee", "level", reason=classification.level, interlocutor=target_id)
    for item in classification.moves:
        if scenario.overrides.classifier_moves.get(item.id) is False:
            continue
        move = rules.moves.get(item.id)
        if move is None or not quoted(item.quote):
            continue
        moves.add(item.id)
        current.moves.append(MoveRecord(turn=current.turn, id=item.id, quote=item.quote))
        for dial, delta in move.deltas.items():
            is_sc_override = item.id in scenario.overrides.moves and dial in scenario.overrides.moves[item.id]
            change.dial(
                dial,
                delta,
                "move",
                interlocutor=target_id,
                ref=item.id,
                quote=item.quote,
                reason="scenario override" if is_sc_override else "",
            )

        if move.say_hint:
            current.cues.append(Cue(kind="hint", text=move.say_hint))
        if move.flag:
            current.flags.append(Flag(turn=current.turn, id=move.flag, quote=item.quote))
            change.add("move", "flag", ref=move.flag, quote=item.quote, interlocutor=target_id)
        if ending := move.ends_session:
            current.flags.append(Flag(turn=current.turn, id=ending.id, quote=item.quote))
            current.outcome = Outcome(id=ending.id, label=ending.label, result=ending.result, turn=current.turn)
            change.add("move", "flag", ref=ending.id, quote=item.quote, interlocutor=target_id)
            change.add("move", "outcome", ref=ending.id, reason=ending.label, interlocutor=target_id)
            return change.done()  # an insult ends the session at once, before anything else is looked at

    # Network influence: constructive moves with a stakeholder soften ALL counterparts, twice at most per stakeholder
    if sh and any(m in CONSTRUCTIVE_STAKEHOLDER_MOVES for m in moves):
        engagements = current.stakeholder_engagements[target_id]
        role_name = sh.get("role", "Stakeholder")
        if engagements <= 2:
            multiplier = 1.0 if engagements == 1 else 0.5
            influence = sh.get("influence", "medium")
            base_rig = -20 if influence == "high" else (-15 if influence == "medium" else -10)
            base_host = -15 if influence == "high" else (-10 if influence == "medium" else -5)
            rig_delta = int(round(base_rig * multiplier))
            host_delta = int(round(base_host * multiplier))
            for cp in scenario.counterparts:
                change.dial(
                    "rigidity",
                    rig_delta,
                    "rule",
                    interlocutor=cp.id,
                    reason=f"Stakeholder {sh.get('role')} endorsed humanitarian position",
                )
                change.dial(
                    "hostility",
                    host_delta,
                    "rule",
                    interlocutor=cp.id,
                    reason=f"Stakeholder {sh.get('role')} endorsed humanitarian position",
                )
            current.cues.append(
                Cue(
                    kind="hint",
                    text=f"Stakeholder {role_name} agreed to leverage influence to soften counterpart resistance.",
                )
            )
        else:
            current.cues.append(
                Cue(
                    kind="hint",
                    text=f"Stakeholder {role_name} has already leveraged maximum influence with the counterparts.",
                )
            )

    # CCHN T14: detect multi-turn tier sequencing from proposals
    if proposals and scenario.issue_tiers:
        past_tiers = {scenario.issue_tiers.get(p.issue) for p in current.proposals if p.turn < current.turn}
        current_tiers = {scenario.issue_tiers.get(p.issue) for p in proposals}
        if (
            3 in current_tiers
            and 1 not in past_tiers
            and "opens_with_tier3" not in moves
            and scenario.overrides.classifier_moves.get("opens_with_tier3") is not False
        ):
            rule = rules.moves.get("opens_with_tier3")
            if rule:
                moves.add("opens_with_tier3")
                quote = next(
                    (
                        p.quote
                        for p in classification.proposals
                        if scenario.issue_tiers.get(p.issue) == 3 and quoted(p.quote)
                    ),
                    "",
                )
                current.moves.append(MoveRecord(turn=current.turn, id="opens_with_tier3", quote=quote))
                for dial, delta in rule.deltas.items():
                    change.dial(dial, delta, "move", interlocutor=target_id, ref="opens_with_tier3", quote=quote)
        elif (
            3 in current_tiers
            and 1 in past_tiers
            and 2 in past_tiers
            and "sequences_by_tier" not in moves
            and scenario.overrides.classifier_moves.get("sequences_by_tier") is not False
        ):
            rule = rules.moves.get("sequences_by_tier")
            if rule:
                moves.add("sequences_by_tier")
                quote = next(
                    (
                        p.quote
                        for p in classification.proposals
                        if scenario.issue_tiers.get(p.issue) == 3 and quoted(p.quote)
                    ),
                    "",
                )
                current.moves.append(MoveRecord(turn=current.turn, id="sequences_by_tier", quote=quote))
                for dial, delta in rule.deltas.items():
                    change.dial(dial, delta, "move", interlocutor=target_id, ref="sequences_by_tier", quote=quote)
    consistency = rules.consistency
    if consistency and not moves & set(consistency.lowering_moves) and current.dials.get(consistency.dial, 100) < 100:
        change.dial(
            consistency.dial,
            consistency.recovery_per_turn,
            "rule",
            interlocutor=target_id,
            reason="coherent message: consistency recovers",
        )
    red_lines = set(scenario.red_lines)
    for line in classification.red_lines:
        if line.text in red_lines and quoted(line.quote):
            current.flags.append(Flag(turn=current.turn, id="red_line_crossed", text=line.text, quote=line.quote))
            current.outcome = Outcome(id="red_line", label="Red line crossed", result="fail", turn=current.turn)
            change.add("rule", "flag", ref="red_line_crossed", quote=line.quote, text=line.text, interlocutor=target_id)
            change.add("rule", "outcome", ref="red_line", reason="Red line crossed", interlocutor=target_id)
            return change.done()
    must_refer = set(scenario.must_refer)
    for line in classification.mandate_breaches:
        if line.text in must_refer and quoted(line.quote):
            current.flags.append(Flag(turn=current.turn, id="mandate_breach", text=line.text, quote=line.quote))
            change.add("rule", "flag", ref="mandate_breach", quote=line.quote, text=line.text, interlocutor=target_id)
    for trigger in [*scenario.triggers, *rules.global_triggers]:
        if matches(trigger.when, current, moves, proposals):
            if hint := trigger.say or trigger.effect:
                current.cues.append(Cue(kind="hint", text=hint))
            if trigger.shift_level and not sh:  # a stakeholder does not steer the negotiation's level
                current.level = trigger.shift_level
                change.add("rule", "level", reason=trigger.shift_level, interlocutor=target_id)
    if not sh:  # hidden interests belong to a counterpart; a stakeholder turn reveals nothing
        _reveal(scenario, rules, change, moves)
    fired = {item.id for item in current.injections}
    for injection in scenario.injections:
        auto = injection.auto
        if (
            auto
            and (auto.at_turn == current.turn or (auto.when is not None and matches(auto.when, current, moves)))
            and injection.id not in fired
        ):
            _fire(change, injection, "auto")
            fired.add(injection.id)
    if not sh:  # outcomes and offers belong to the counterparts; a stakeholder turn never grants or fails them
        _decide(scenario, rules, change)
        if current.outcome is None:
            _offer(scenario, current, state.offered)
        else:
            current.offered = None
    if target_id in current.counterpart_dials:
        current.counterpart_dials[target_id] = dict(current.dials)
    for cue in current.cues:  # cues are replaced every turn; the events keep them for review
        change.add("cue", "cue", cue=cue, interlocutor=target_id)
    return change.done()


def nudge(scenario: Scenario, rules: Rules, state: State) -> Step:
    """An inactivity/silence turn: raises hostility, injects the inactivity prompt,
    evaluates triggers, reveals, auto injections, and checks fail outcomes."""
    if state.outcome:
        raise EngineError("The session has ended")
    change = _Change(state)
    current = change.state
    current.turn += 1
    current.goal_requested = False
    current.cues = []
    current.offered = None

    penalty = scenario.timing.silence.penalty  # None: the built-in 5
    if "hostility" in current.dials:
        change.dial("hostility", penalty or 5, "auto", reason="Trainee silence / hesitation")

    nudge_instruction = (
        "The delegate (the person you are speaking with) has remained completely silent and hesitant. "
        "Remind them firmly of your limited time and urgent responsibilities, "
        "show your impatience, and demand that they state their proposal or conclude the meeting."
    )
    record = InjectionRecord(
        id=f"nudge_{current.turn}",
        label="Inactivity prompt",
        instruction=nudge_instruction,
        source="auto",
        turn=current.turn,
    )
    current.injections.append(record)
    change.add("auto", "injection", ref=record.id)

    moves: set[str] = set()
    proposals: list[ProposalLine] = []
    sh = scenario.stakeholder_for(state.active_interlocutor)

    for trigger in [*scenario.triggers, *rules.global_triggers]:
        if matches(trigger.when, current, moves, proposals):
            if hint := trigger.say or trigger.effect:
                current.cues.append(Cue(kind="hint", text=hint))
            if trigger.shift_level and not sh:  # a stakeholder does not steer the negotiation's level
                current.level = trigger.shift_level
                change.add("rule", "level", reason=trigger.shift_level)
    if not sh:  # hidden interests belong to a counterpart; a nudge while one is selected reveals nothing
        _reveal(scenario, rules, change, moves)
    fired = {item.id for item in current.injections}
    for injection in scenario.injections:
        auto = injection.auto
        if (
            auto
            and (auto.at_turn == current.turn or (auto.when is not None and matches(auto.when, current, moves)))
            and injection.id not in fired
        ):
            _fire(change, injection, "auto")
            fired.add(injection.id)
    if not sh:  # outcomes and offers belong to the counterparts; a stakeholder nudge never grants or fails them
        _decide(scenario, rules, change)
        if current.outcome is None:
            _offer(scenario, current, state.offered)
        else:
            current.offered = None
    for cue in current.cues:
        change.add("cue", "cue", cue=cue)
    return change.done()


def grantable(state: State) -> bool:
    """An outcome can be granted only if it was on the table before this turn: the counterpart offers, the trainee
    then accepts or asks, and the counterpart says yes. A yes in the same turn as the offer is the cue talking."""
    return state.offered is not None and state.outcome is None and state.offered.turn < state.turn


def grant(scenario: Scenario, state: State, quote: str) -> Step:
    """The counterpart itself said yes to the outcome on the table; it counts only if the dials still support it.
    A success ends the session; a partial outcome becomes a milestone and the session goes on."""
    offered = state.offered
    if offered is None or not grantable(state):
        return Step(state.model_copy(deep=True))
    rule = next((item for item in scenario.outcomes if item.id == offered.id), None)
    if rule is None or not matches(without_goal(rule.when), state):
        return Step(state.model_copy(deep=True))
    change = _Change(state)
    current = change.state
    entry = Outcome(id=rule.id, label=rule.label, result=rule.result, turn=current.turn)
    if rule.result == "partial":
        current.reached.append(entry)
    else:
        current.outcome = entry
    current.offered = None
    change.add("grant", "grant", ref=rule.id, quote=quote)
    return change.done()


def inject(scenario: Scenario, state: State, injection_id: str, source: TwistSource = "trainer") -> Step:
    """A preset twist. It never ends the session: the outcome is decided on the next trainee message."""
    if state.outcome:
        raise EngineError("The session has ended")
    injection = next((item for item in scenario.injections if item.id == injection_id), None)
    if injection is None:
        raise EngineError(f"Unknown injection {injection_id}")
    change = _Change(state)
    _fire(change, injection, source)
    return change.done()


def inject_text(state: State, original: str, rewritten: str, bias: dict[str, Any] | None) -> Step:
    """A free-text trainer twist, already rewritten by the director and checked for bias. It never ends the
    session: the outcome is decided on the next trainee message."""
    if state.outcome:
        raise EngineError("The session has ended")
    change = _Change(state)
    current = change.state
    record = InjectionRecord(
        id=f"free_{len(current.injections) + 1}",
        label="Trainer twist",
        instruction=rewritten,
        source="trainer",
        turn=current.turn,
        original=original,
        rewritten=rewritten,
        bias=bias,
    )
    current.injections.append(record)
    change.add("trainer", "injection", ref=record.id)
    return change.done()


def set_dial(state: State, dial: str, value: int) -> Step:
    """Trainer override, clamped to 0..100. It never ends the session."""
    if dial not in state.dials:
        raise EngineError(f"Unknown dial {dial}")
    change = _Change(state)
    target = max(0, min(100, int(value)))
    change.dial(dial, target - change.state.dials[dial], "trainer", reason="manual override")
    return change.done()


def end(state: State) -> Step:
    """The player stops the session. Result "ended"; milestones already reached are kept."""
    if state.outcome:
        raise EngineError("The session has ended")
    change = _Change(state)
    current = change.state
    current.outcome = Outcome(
        id="ended_by_trainee", label="Session ended by the trainee", result="ended", turn=current.turn
    )
    current.offered = None
    change.add("trainee", "ended", reason="ended the session")
    return change.done()


def time_up(state: State, *, fail: bool) -> Step:
    """The scenario's minutes ran out and its rules say the meeting ends. As a failure (`fail`) or without a result
    ("ended", as when the trainee stops). Milestones already reached are kept."""
    if state.outcome:
        raise EngineError("The session has ended")
    change = _Change(state)
    current = change.state
    label = "Time ran out without an agreement" if fail else "Time ran out"
    current.outcome = Outcome(id="time_up", label=label, result="fail" if fail else "ended", turn=current.turn)
    current.offered = None
    change.add("rule", "outcome", ref="time_up", reason=label)
    return change.done()


def is_red_line(outcome: Outcome | None) -> bool:
    """A red line or an insult: the session ends on the banner alone and the counterpart says nothing more."""
    return outcome is not None and (outcome.id == "red_line" or outcome.label.startswith("Red line crossed"))


def _reveal(scenario: Scenario, rules: Rules, change: _Change, moves: set[str]) -> None:
    current = change.state
    target_cp = scenario.counterpart_for(current.active_interlocutor)
    for interest in target_cp.hidden_interests:
        if interest.id in current.revealed:
            continue
        condition = interest.reveal_when
        if condition is None:
            condition = rules.hidden_interest_reveal_defaults.get(interest.layer, NEVER)
        if matches(condition, current, moves):
            current.revealed.append(interest.id)
            if target_cp.id in current.counterpart_revealed:
                current.counterpart_revealed[target_cp.id].append(interest.id)
            change.add("reveal", "reveal", ref=interest.id, interlocutor=target_cp.id)


def _fire(change: _Change, injection: Injection, source: TwistSource) -> None:
    current = change.state
    if injection.id in {item.id for item in current.injections}:
        return
    current.injections.append(
        InjectionRecord(
            id=injection.id, label=injection.label, instruction=injection.instruction, source=source, turn=current.turn
        )
    )
    change.add(source, "injection", ref=injection.id)
    for dial, delta in injection.dials.items():
        change.dial(dial, delta, source, ref=injection.id)


def _decide(scenario: Scenario, rules: Rules, change: _Change) -> None:
    """Fail outcomes, global ones first; the first match ends the session. Success and partial outcomes end only
    when the counterpart itself says yes (grant)."""
    current = change.state
    if current.outcome:
        return
    for rule in [*rules.global_outcomes, *scenario.outcomes]:
        if rule.result != "fail":
            continue
        if matches(rule.when, current):
            current.outcome = Outcome(id=rule.id, label=rule.label, result=rule.result, turn=current.turn)
            change.add("rule", "outcome", ref=rule.id, reason=rule.label)
            return


def _offer(scenario: Scenario, current: State, previous: Offer | None) -> None:
    """Put the best success or partial outcome whose numbers are in range on the table. It is cued every turn while
    pending (a single cue was once ignored); once the trainee asks on a later turn, the counterpart is told to agree.
    A partial outcome already reached is not offered again."""
    done = {item.id for item in current.reached}
    for item in current.reached:
        current.cues.append(Cue(kind="reached", label=item.label))
    for rule in scenario.outcomes:
        if rule.id in done or rule.result == "fail" or not matches(without_goal(rule.when), current):
            continue
        result: Literal["success", "partial"] = "success" if rule.result == "success" else "partial"
        if previous is not None and previous.id == rule.id:
            first_turn, fresh = previous.turn, False
        else:
            first_turn, fresh = current.turn, True
        current.offered = Offer(id=rule.id, label=rule.label, result=result, turn=first_turn)
        kind: Literal["offer", "agree_now"] = "agree_now" if current.goal_requested and not fresh else "offer"
        current.cues.append(Cue(kind=kind, label=rule.label))
        return
    current.offered = None


DE_ESCALATION_STEP_MOVES: dict[int, set[str]] = {
    1: {"pause_and_acknowledge", "acknowledges_emotion"},
    2: {"reformulates_with_check"},
    3: {"sets_emotion_aside"},
    4: {"reframes_core_issue"},
    5: {"oco_questions"},
    6: {"offers_options"},
}


def de_escalation_steps_completed(state: State) -> list[int]:
    """Which of the six CCHN T8 de-escalation steps occurred in sequence in this session."""
    steps_found: list[int] = []
    current_step = 1
    for move in state.moves:
        if current_step in DE_ESCALATION_STEP_MOVES and move.id in DE_ESCALATION_STEP_MOVES[current_step]:
            steps_found.append(current_step)
            current_step += 1
            if current_step > 6:
                break
    return steps_found
