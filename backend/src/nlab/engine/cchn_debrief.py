"""CCHN Debrief and Reflection analysis engine.

Computes comprehensive CCHN doctrine debrief metrics:
1. Agreement check (T7: 5 criteria & drafted terms sheet)
2. Zones (T13/T14: A-B-C scale, areas D/E/F, Tier-3 issues parking)
3. Level timeline (T4: Political/Professional/Technical navigation and shifts)
4. Iceberg depth (T9: Position/Reasoning/Values layers vs preparation guesses)
5. De-escalation report (T8: Hostility spikes, 6-step protocol, anti-patterns)
6. Preparation vs reality (Comparison of Naivasha Grid modules against session events)
7. Reflection questions (T6 conduct/debrief checklist and self-assessment prompts)
8. Competences (Rubric dimensions mapped to Core, Advanced, Expert tiers)
9. Knowledge links (Doctrine citations and doc references)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from nlab.engine.ops import DE_ESCALATION_STEP_MOVES
from nlab.engine.state import State

STEP_NAME_BY_NUM: dict[int, str] = {
    1: "1. Pause & acknowledge emotion",
    2: "2. Reformulate statement",
    3: "3. Capture emotion & set aside",
    4: "4. Reframe conversation",
    5: "5. Question O/C/O",
    6: "6. Discuss options",
}

# ---------------------------------------------------------------------------
# Schemas for CCHN Debrief Analysis
# ---------------------------------------------------------------------------


class AgreementCriterionOut(BaseModel):
    id: str
    label: str
    score: int = Field(ge=1, le=5)
    status: Literal["met", "partial", "unmet"]
    finding: str
    evidence: str | None = None


class AgreementCheckOut(BaseModel):
    is_deal: bool
    terms_sheet: list[str] = Field(default_factory=list)
    criteria: list[AgreementCriterionOut] = Field(default_factory=list)
    overall_score: int = Field(default=0, ge=0, le=100)
    doc_id: str = "cchn-tool-07"


class Tier3IssueOut(BaseModel):
    id: str
    label: str
    status: Literal["parked", "conceded", "unresolved", "not_applicable"]
    finding: str


class ZonesOut(BaseModel):
    zone: Literal["E", "D", "F", "RED", "NO_DEAL"]
    zone_label: str
    description: str
    scale: dict[str, dict[str, str]]
    tier_3_issues: list[Tier3IssueOut] = Field(default_factory=list)
    tier_3_parked: bool = True
    doc_id: str = "cchn-tool-13"


class LevelTimelineEntryOut(BaseModel):
    turn: int
    level: str  # political | professional | technical
    speaker: Literal["trainee", "counterpart", "system"]
    shifted: bool = False
    direction: Literal["politicize", "depoliticize"] | None = None
    matched: bool = True
    note: str = ""


class LevelTimelineOut(BaseModel):
    start_level: str
    final_level: str
    entries: list[LevelTimelineEntryOut] = Field(default_factory=list)
    summary: str = ""
    doc_id: str = "cchn-tool-04"


class IcebergLayerOut(BaseModel):
    layer: Literal["position", "reasoning", "motives_values"]
    label: str
    reached: bool = False
    counterpart_content: list[str] = Field(default_factory=list)
    prep_guess: str | None = None
    accuracy_note: str = ""


class IcebergDepthOut(BaseModel):
    layers: list[IcebergLayerOut] = Field(default_factory=list)
    max_layer_reached: Literal["none", "position", "reasoning", "motives_values"] = "none"
    summary: str = ""
    doc_id: str = "cchn-tool-09"


class DeescalationIncidentOut(BaseModel):
    turn: int
    hostility_level: int
    trigger: str
    trainee_turn: int
    trainee_quote: str
    steps_observed: list[str] = Field(default_factory=list)
    anti_patterns_observed: list[str] = Field(default_factory=list)
    hostility_after: int
    outcome: Literal["de-escalated", "escalated", "neutral"]


class DeescalationReportOut(BaseModel):
    incidents: list[DeescalationIncidentOut] = Field(default_factory=list)
    summary: str = ""
    doc_id: str = "cchn-tool-08"


class PrepVsRealityModuleOut(BaseModel):
    module_id: str
    label: str
    prepared: bool
    planned: str | None = None
    reality: str = ""
    alignment: Literal["aligned", "diverged", "untested", "skipped"]
    insight: str = ""


class PrepVsRealityOut(BaseModel):
    has_preparation: bool
    modules: list[PrepVsRealityModuleOut] = Field(default_factory=list)
    summary: str = ""
    doc_id: str = "cchn-naivasha-grid"


class ReflectionQuestionOut(BaseModel):
    id: str
    prompt: str
    guidance: str
    answer: str | None = None


class ReflectionSectionOut(BaseModel):
    questions: list[ReflectionQuestionOut] = Field(default_factory=list)
    completed: bool = False
    doc_id: str = "cchn-tool-06"


class CompetenceDimensionOut(BaseModel):
    id: str
    label: str
    score: int | None = None
    quote: str | None = None


class CompetenceTierOut(BaseModel):
    tier: Literal["core", "advanced", "expert"]
    label: str
    dimensions: list[CompetenceDimensionOut] = Field(default_factory=list)
    summary: str = ""


class CompetencesSectionOut(BaseModel):
    tiers: list[CompetenceTierOut] = Field(default_factory=list)
    doc_id: str = "cchn-competences"


class KnowledgeLinkOut(BaseModel):
    id: str
    title: str
    framework: str
    citation: str
    summary: str
    tags: list[str] = Field(default_factory=list)


class CchnDebriefOut(BaseModel):
    agreement_check: AgreementCheckOut | None = None
    zones: ZonesOut | None = None
    level_timeline: LevelTimelineOut | None = None
    iceberg_depth: IcebergDepthOut | None = None
    deescalation_report: DeescalationReportOut | None = None
    prep_vs_reality: PrepVsRealityOut | None = None
    reflection: ReflectionSectionOut | None = None
    competences: CompetencesSectionOut | None = None
    knowledge_links: list[KnowledgeLinkOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# CCHN Doctrine Knowledge Links Catalog
# ---------------------------------------------------------------------------

DOCTRINE_LINKS: dict[str, KnowledgeLinkOut] = {
    "cchn-tool-07": KnowledgeLinkOut(
        id="cchn-tool-07",
        title="Clarifying the Terms of the Transaction",
        framework="CCHN Field Manual on Frontline Humanitarian Negotiation",
        citation="CCHN Field Manual (2019), Tool 7, pp. 168-177; CCHN Negotiator Handbook, Tool 7, pp. 32-35",
        summary=(
            "An agreement is only as good as its implementation. Check the terms against five criteria "
            "(clear language, roles and tasks, reciprocal and sequenced commitments, a process for divergence, "
            "the power relationship) before calling it a deal."
        ),
        tags=["terms", "agreement", "implementation", "reciprocity", "sequencing", "divergence", "power-relationship"],
    ),
    "cchn-tool-13": KnowledgeLinkOut(
        id="cchn-tool-13",
        title="Identifying the Shared Benefit of the Negotiation",
        framework="CCHN Field Manual on Frontline Humanitarian Negotiation",
        citation="CCHN Field Manual (2019), Tool 13, pp. 277-310; CCHN Negotiator Handbook, Tool 13, pp. 63-69",
        summary=(
            "Frame options along the A-B-C scale (ideal outcome, bottom line, red line) and navigate "
            "zones D, E and F. Values-based Tier-3 issues must be parked at first rather than forced into "
            "transactional trade-offs."
        ),
        tags=["shared_benefit", "bottom_lines", "red_lines", "zones", "tier_3_parking"],
    ),
    "cchn-tool-04": KnowledgeLinkOut(
        id="cchn-tool-04",
        title="Typology of Humanitarian Negotiation",
        framework="CCHN Field Manual on Frontline Humanitarian Negotiation",
        citation="CCHN Field Manual (2019), Tool 4, pp. 106-136; CCHN Facilitator Handbook, Session 5, pp. 49-58",
        summary=(
            "Distinguish negotiations by level: Political (mandates, legitimacy, high-level principles), "
            "Professional (standards, methods, operational modalities), and Technical (practical logistics, "
            "facts, timing). Politicize or depoliticize purposefully to unlock progress."
        ),
        tags=["typology", "levels", "political", "professional", "technical", "politicizing", "depoliticizing"],
    ),
    "cchn-tool-09": KnowledgeLinkOut(
        id="cchn-tool-09",
        title="Analyzing the Position of the Counterpart",
        framework="CCHN Field Manual on Frontline Humanitarian Negotiation",
        citation="CCHN Field Manual (2019), Tool 9, pp. 198-217; CCHN Negotiator Handbook, Tool 9, pp. 42-46",
        summary=(
            "The negotiation iceberg: surface positions (WHAT), tactical reasoning (HOW), and underlying "
            "motives, values, and identity (WHY). Build trust to reach deeper layers and uncover what the "
            "counterpart is not overtly communicating."
        ),
        tags=["iceberg", "counterpart_analysis", "positions", "reasoning", "motives_values"],
    ),
    "cchn-tool-08": KnowledgeLinkOut(
        id="cchn-tool-08",
        title="Addressing the Human Elements of the Transaction",
        framework="CCHN Field Manual on Frontline Humanitarian Negotiation",
        citation="CCHN Field Manual (2019), Tool 8, pp. 152-188; CCHN Negotiator Handbook, Tool 8, pp. 36-39",
        summary=(
            "De-escalate difficult moments using the 6-step cycle: Pause & acknowledge emotion, Reformulate, "
            "Capture emotion & set aside, Reframe, Open/Close/Open questions, Discuss options. Avoid counter-arguing, "
            "false understanding, and apologizing."
        ),
        tags=["de_escalation", "active_listening", "hostility", "emotions", "human_elements"],
    ),
    "cchn-naivasha-grid": KnowledgeLinkOut(
        id="cchn-naivasha-grid",
        title="The Naivasha Grid: Planning Frontline Negotiation",
        framework="CCHN Field Manual on Frontline Humanitarian Negotiation",
        citation="CCHN Field Manual (2019), pp. 29-36; CCHN Facilitator Handbook, Session 2, pp. 15-20",
        summary=(
            "The Naivasha Grid organizes negotiation planning into Context Analysis, Tactical Plan, and "
            "Transaction. It serves as both a planning tool ahead of the meeting and an analytical tool to "
            "identify what is blocking progress."
        ),
        tags=["naivasha_grid", "planning", "preparation", "context_analysis", "tactical_plan", "transaction"],
    ),
    "cchn-tool-06": KnowledgeLinkOut(
        id="cchn-tool-06",
        title="Creating a Conducive Environment for the Transaction",
        framework="CCHN Field Manual on Frontline Humanitarian Negotiation",
        citation="CCHN Field Manual (2019), Tool 6, pp. 152-167; CCHN Negotiator Handbook, Tool 6, pp. 29-31",
        summary=(
            "Set up a safe space for dialogue. Actively perceive rather than actively persuade, bring up "
            "options rather than rigid solutions, and conclude with agreed next steps."
        ),
        tags=["conducive_environment", "conduct", "debrief_checklist", "active_perceiving", "next_steps"],
    ),
    "cchn-competences": KnowledgeLinkOut(
        id="cchn-competences",
        title="Competences of Humanitarian Negotiators",
        framework="CCHN Field Manual on Frontline Humanitarian Negotiation",
        citation="CCHN Field Manual (2019), Annex pp. 380-383",
        summary=(
            "The CCHN Competence Chart establishes shared professional objectives across Core, Advanced, and "
            "Expert tiers, encompassing Knowledge, Attitudes, and Skills required for complex frontline negotiation."
        ),
        tags=["competences", "core", "advanced", "expert", "knowledge", "attitudes", "skills"],
    ),
}


# ---------------------------------------------------------------------------
# Analytics Computation Helpers
# ---------------------------------------------------------------------------


def compute_agreement_check(
    content: Mapping[str, Any],
    state: State,
    turns: Sequence[Any],
) -> AgreementCheckOut:
    """Computes Agreement check (T7) on the five criteria and drafts a terms sheet."""
    is_deal = False
    if (state.outcome and state.outcome.result in ("success", "partial")) or bool(state.proposals):
        is_deal = True

    terms_sheet: list[str] = []
    checklist_raw = content.get("implementation_checklist") or []
    checklist_map = {item.get("id", ""): item.get("text", "") for item in checklist_raw if isinstance(item, dict)}

    # Gather covered terms from checklist
    for detail_id in state.covered_details:
        label = checklist_map.get(detail_id) or detail_id.replace("_", " ").capitalize()
        terms_sheet.append(f"Operational detail clarified: {label}")

    # Gather proposals
    for prop in state.proposals:
        terms_sheet.append(f"Agreed position on {prop.issue}: {prop.line}")

    if state.outcome and state.outcome.label:
        terms_sheet.append(f"Outcome milestone: {state.outcome.label}")

    # Evaluate the 5 criteria
    covered_count = len(state.covered_details)
    checklist_total = max(len(checklist_raw), 1)
    detail_ratio = covered_count / checklist_total

    # 1. Clear language
    if detail_ratio >= 0.7:
        c1_score = 5
        c1_status: Literal["met", "partial", "unmet"] = "met"
        c1_finding = (
            f"Operational terms were clearly articulated ({covered_count}/{checklist_total} "
            "checklist items established in specific operational language)."
        )
    elif detail_ratio >= 0.35:
        c1_score = 3
        c1_status = "partial"
        c1_finding = (
            f"Partially specified terms ({covered_count}/{checklist_total} checklist items). "
            "Some implementation modalities remained ambiguous."
        )
    else:
        c1_score = 2 if is_deal else 1
        c1_status = "unmet"
        c1_finding = (
            "Vague commitments with substantial operational ambiguity; critical logistical "
            "details were left unaddressed."
        )

    # 2. Roles and tasks
    has_proposals = len(state.proposals) > 0
    if is_deal and (has_proposals or detail_ratio >= 0.5):
        c2_score = 4
        c2_status = "met"
        c2_finding = (
            "Distinct roles and operational tasks were defined for both the humanitarian team and the counterpart."
        )
    elif is_deal:
        c2_score = 3
        c2_status = "partial"
        c2_finding = (
            "Roles were partially assigned, but specific execution responsibilities require further clarification."
        )
    else:
        c2_score = 1
        c2_status = "unmet"
        c2_finding = "No operational roles or tasks were established."

    # 3. Reciprocity and sequence
    moves_set = {m.id for m in state.moves}
    has_sequence = "defines_sequence" in moves_set or detail_ratio >= 0.6
    if is_deal and has_sequence:
        c3_score = 5
        c3_status = "met"
        c3_finding = "Reciprocal commitments were established with clear chronological sequencing of handoffs."
    elif is_deal:
        c3_score = 3
        c3_status = "partial"
        c3_finding = (
            "Commitments were identified, but sequential dependency and mutual conditional steps were left loose."
        )
    else:
        c3_score = 1
        c3_status = "unmet"
        c3_finding = "Lacks reciprocal sequencing between parties."

    # 4. Divergence process
    has_divergence_move = "proposes_divergence_mechanism" in moves_set
    divergence_in_text = False
    for t in turns:
        txt = (getattr(t, "trainee_text", None) or "").lower()
        if any(
            w in txt
            for w in ("hotline", "pause and meet", "divergence", "misunderstanding", "contact person", "liaison")
        ):
            divergence_in_text = True
            break

    if has_divergence_move or divergence_in_text:
        c4_score = 5
        c4_status = "met"
        c4_finding = (
            "Proactively established a dispute resolution mechanism or direct communication link to "
            "handle implementation divergences without escalation."
        )
    elif is_deal:
        c4_score = 2
        c4_status = "unmet"
        c4_finding = (
            "No practical process was established for handling misunderstandings or checkpoint "
            "disputes during implementation."
        )
    else:
        c4_score = 1
        c4_status = "unmet"
        c4_finding = "No divergence handling mechanism was discussed."

    # 5. Power and responsibility
    has_red_line_flag = any(f.id == "red_line" for f in state.flags)
    has_mandate_flag = any(f.id in ("mandate", "unauthorized_commitment") for f in state.flags)
    if is_deal and not has_red_line_flag and not has_mandate_flag:
        c5_score = 5
        c5_status = "met"
        c5_finding = (
            "Responsibility was appropriately calibrated according to each party's authority, "
            "strictly preserving mandate boundaries."
        )
    elif has_mandate_flag:
        c5_score = 2
        c5_status = "unmet"
        c5_finding = "Over-committed beyond mandated authority, distorting institutional responsibility."
    elif is_deal:
        c5_score = 3
        c5_status = "partial"
        c5_finding = "Power relationships were handled, though mandate limits were strained."
    else:
        c5_score = 1
        c5_status = "unmet"
        c5_finding = "Power dynamics remained unaddressed."

    criteria = [
        AgreementCriterionOut(
            id="clear_language",
            label="Clear Language & Commitments",
            score=c1_score,
            status=c1_status,
            finding=c1_finding,
        ),
        AgreementCriterionOut(
            id="roles_and_tasks",
            label="Roles and Tasks of Parties",
            score=c2_score,
            status=c2_status,
            finding=c2_finding,
        ),
        AgreementCriterionOut(
            id="reciprocity_and_sequence",
            label="Reciprocity and Sequence",
            score=c3_score,
            status=c3_status,
            finding=c3_finding,
        ),
        AgreementCriterionOut(
            id="divergence_process",
            label="Process to Handle Divergence",
            score=c4_score,
            status=c4_status,
            finding=c4_finding,
        ),
        AgreementCriterionOut(
            id="power_and_responsibility",
            label="Calibrated Power & Responsibility",
            score=c5_score,
            status=c5_status,
            finding=c5_finding,
        ),
    ]

    overall = int(sum(c.score for c in criteria) / len(criteria) * 20)

    return AgreementCheckOut(
        is_deal=is_deal,
        terms_sheet=terms_sheet,
        criteria=criteria,
        overall_score=overall,
        doc_id="cchn-tool-07",
    )


def compute_zones(
    content: Mapping[str, Any],
    state: State,
) -> ZonesOut:
    """Computes Zones (T13/T14): A-B-C scale, areas D/E/F, and Tier-3 issue parking."""
    counterpart = (content.get("counterparts") or [{}])[0]
    counterpart_iceberg = counterpart.get("iceberg") or {}

    trainee_scale = {
        "ideal_a": content.get("title", "Optimal operational access without concessions"),
        "bottom_line_b": "Limit of negotiator's delegated flexibility (seeking mandator review beyond)",
        "red_line_c": "Mandated institutional red lines (non-negotiable limits of mandate)",
    }

    cp_stated = (counterpart_iceberg.get("position") or {}).get("stated", "Counterpart initial position")
    counterpart_scale = {
        "ideal_a": cp_stated,
        "bottom_line_b": "Counterpart tactical flexibility limit",
        "red_line_c": "Counterpart authority limit / superior authorization required",
    }

    scale = {
        "trainee": trainee_scale,
        "counterpart": counterpart_scale,
    }

    # Evaluate Zone
    has_red_line_flag = any(f.id == "red_line" for f in state.flags)
    has_mandate_flag = any(f.id in ("mandate", "unauthorized_commitment") for f in state.flags)

    if has_red_line_flag:
        zone = "RED"
        zone_label = "Outside Mandate (Red Line Breach)"
        description = (
            "An institutional red line was crossed. In CCHN doctrine, red lines are non-negotiable "
            "limits set by the mandator that cannot be compromised."
        )
    elif has_mandate_flag:
        zone = "F"
        zone_label = "Area F: Below Negotiator Bottom Line"
        description = (
            "The agreement or commitments fell below the negotiator's bottom line into Area F, requiring "
            "formal review and fresh instructions from the hierarchy."
        )
    elif state.outcome and state.outcome.result in ("success", "partial"):
        zone = "E"
        zone_label = "Area E: Within Bottom Lines (Common Shared Space)"
        description = (
            "The compromise landed squarely in Area E between the bottom lines of both parties — "
            "the zone of optimal shared benefit without breaching mandate limits."
        )
    elif state.turn > 0:
        zone = "D"
        zone_label = "Area D: Outside Counterpart Comfort / Divergent"
        description = "The dialogue ended without finding convergent ground within the Common Shared Space."
    else:
        zone = "NO_DEAL"
        zone_label = "No Agreement Reached"
        description = "The session concluded before an agreement could be crystallized."

    # Tier-3 Issues Parking Analysis
    issues_raw = content.get("issues") or []
    tier_3_issues: list[Tier3IssueOut] = []
    tier_3_parked = True

    for issue in issues_raw:
        if isinstance(issue, dict) and int(issue.get("tier", 1)) == 3:
            issue_id = issue.get("id", "tier3_issue")
            issue_text = issue.get("text", issue_id)
            # Check if this issue was conceded or forced
            conceded = any(p.issue == issue_id for p in state.proposals)
            if conceded:
                tier_3_parked = False
                tier_3_issues.append(
                    Tier3IssueOut(
                        id=issue_id,
                        label=issue_text,
                        status="conceded",
                        finding=(
                            f"Tier-3 issue '{issue_text}' was drawn into active concessions rather than parked, "
                            "increasing organizational risk."
                        ),
                    )
                )
            else:
                tier_3_issues.append(
                    Tier3IssueOut(
                        id=issue_id,
                        label=issue_text,
                        status="parked",
                        finding=(
                            f"Tier-3 issue '{issue_text}' was appropriately parked "
                            "(kept present but kept aside from transactional trade-offs)."
                        ),
                    )
                )

    if not tier_3_issues:
        tier_3_issues.append(
            Tier3IssueOut(
                id="general_tier3",
                label="Values and Core Identity Issues",
                status="not_applicable",
                finding="No explicit Tier-3 ideological issues were contested in this scenario.",
            )
        )

    return ZonesOut(
        zone=zone,
        zone_label=zone_label,
        description=description,
        scale=scale,
        tier_3_issues=tier_3_issues,
        tier_3_parked=tier_3_parked,
        doc_id="cchn-tool-13",
    )


def compute_level_timeline(
    content: Mapping[str, Any],
    state: State,
    turns: Sequence[Any],
) -> LevelTimelineOut:
    """Computes Level Timeline (T4): tracking conversation movements between
    Political, Professional, and Technical levels."""
    start_level = (content.get("negotiation") or {}).get("start_level", "technical")
    entries: list[LevelTimelineEntryOut] = []
    current_level = start_level

    # Turn 0: Counterpart opening
    entries.append(
        LevelTimelineEntryOut(
            turn=0,
            level=start_level,
            speaker="counterpart",
            shifted=False,
            direction=None,
            matched=True,
            note=f"Negotiation opened at the {start_level} level.",
        )
    )

    level_hierarchy = {"technical": 1, "professional": 2, "political": 3}

    for turn in turns:
        t_num = getattr(turn, "number", 0)
        if t_num == 0:
            continue

        turn_state = getattr(turn, "engine_state_after", {}) or {}
        new_level = turn_state.get("level", current_level)
        shifted = new_level != current_level

        direction: Literal["politicize", "depoliticize"] | None = None
        if shifted:
            old_rank = level_hierarchy.get(current_level, 1)
            new_rank = level_hierarchy.get(new_level, 1)
            direction = "politicize" if new_rank > old_rank else "depoliticize"

        # Check who moved it
        classification = getattr(turn, "classification", {}) or {}
        moves = classification.get("moves") or []
        trainee_driven = any(m in ("politicizes", "depoliticizes", "appeals_to_principles") for m in moves)
        speaker: Literal["trainee", "counterpart", "system"] = "trainee" if trainee_driven else "counterpart"

        note = f"Conversation remained at {new_level} level."
        if shifted:
            if direction == "politicize":
                note = f"Level shifted up to {new_level} (politicizing dialogue around principles/authority)."
            else:
                note = f"Level shifted down to {new_level} (depoliticizing dialogue toward operational facts)."

        entries.append(
            LevelTimelineEntryOut(
                turn=t_num,
                level=new_level,
                speaker=speaker,
                shifted=shifted,
                direction=direction,
                matched=True,
                note=note,
            )
        )
        current_level = new_level

    final_level = current_level
    summary = f"The negotiation started at the {start_level} level and concluded at the {final_level} level."
    if any(e.shifted for e in entries):
        summary += " Dialogue successfully navigated between levels to unlock deadlock."
    else:
        summary += f" Dialogue remained consistently anchored at the {start_level} level throughout the exchange."

    return LevelTimelineOut(
        start_level=start_level,
        final_level=final_level,
        entries=entries,
        summary=summary,
        doc_id="cchn-tool-04",
    )


def compute_iceberg_depth(
    content: Mapping[str, Any],
    state: State,
    preparation: Mapping[str, Any] | None,
) -> IcebergDepthOut:
    """Computes Iceberg Depth (T9): which layers were reached vs trainee preparation guesses."""
    counterpart = (content.get("counterparts") or [{}])[0]
    counterpart_iceberg = counterpart.get("iceberg") or {}
    hidden_interests = counterpart.get("hidden_interests") or []

    # Position content (Level 1)
    pos_text = (counterpart_iceberg.get("position") or {}).get("stated", "Stated counterpart demands")
    # Reasoning content (Level 2)
    reasoning_items = [h.get("text", "") for h in hidden_interests if h.get("layer") == "reasoning"]
    # Motives/Values content (Level 3)
    values_items = [h.get("text", "") for h in hidden_interests if h.get("layer") in ("values", "motives_values")]

    revealed_set = set(state.revealed)
    reasoning_reached = any(h.get("id") in revealed_set for h in hidden_interests if h.get("layer") == "reasoning")
    values_reached = any(
        h.get("id") in revealed_set for h in hidden_interests if h.get("layer") in ("values", "motives_values")
    )

    # Prep guesses
    prep_data = (preparation or {}).get("counterpart_iceberg") or {}
    guess_what = prep_data.get("what")
    guess_how = prep_data.get("how")
    guess_why = prep_data.get("why")

    # Layer 1: Position
    l1_note = "Position was overt and explored during dialogue."
    if guess_what:
        l1_note += " Trainee's preparation accurately identified the counterpart's core initial stance."
    layer1 = IcebergLayerOut(
        layer="position",
        label="Level 1: Stated Position (WHAT)",
        reached=True,
        counterpart_content=[pos_text],
        prep_guess=guess_what,
        accuracy_note=l1_note,
    )

    # Layer 2: Reasoning
    l2_note = (
        "Tactical reasoning was revealed through trust and open inquiry."
        if reasoning_reached
        else "Tactical reasoning remained unrevealed; counterpart's operational logic was not fully unpacked."
    )
    if guess_how:
        l2_note += " Preparation anticipated key operational constraints."
    layer2 = IcebergLayerOut(
        layer="reasoning",
        label="Level 2: Tactical Reasoning (HOW)",
        reached=reasoning_reached,
        counterpart_content=reasoning_items or ["Operational and logistical constraints"],
        prep_guess=guess_how,
        accuracy_note=l2_note,
    )

    # Layer 3: Values & Motives
    l3_note = (
        "Deepest layer reached: underlying motives and institutional identity were addressed."
        if values_reached
        else "Underlying motives and institutional fears were not accessed during the simulation."
    )
    if guess_why:
        l3_note += " Trainee's prep hypothesized underlying identity and security motivations."
    layer3 = IcebergLayerOut(
        layer="motives_values",
        label="Level 3: Motives & Values (WHY)",
        reached=values_reached,
        counterpart_content=values_items or ["Core institutional values, fears, and community reputation"],
        prep_guess=guess_why,
        accuracy_note=l3_note,
    )

    layers = [layer1, layer2, layer3]

    max_layer: Literal["none", "position", "reasoning", "motives_values"] = "none"
    if values_reached:
        max_layer = "motives_values"
    elif reasoning_reached:
        max_layer = "reasoning"
    elif state.turn > 0:
        max_layer = "position"

    summary = f"Reached depth: {max_layer.replace('_', ' ').title()}."
    if max_layer == "motives_values":
        summary += " Full depth of the counterpart iceberg was uncovered, enabling high-trust solutions."
    elif max_layer == "reasoning":
        summary += " Successfully moved below the surface position to uncover operational reasoning."
    else:
        summary += " Exchange remained primarily at the surface position level."

    return IcebergDepthOut(
        layers=layers,
        max_layer_reached=max_layer,
        summary=summary,
        doc_id="cchn-tool-09",
    )


def compute_deescalation_report(
    turns: Sequence[Any],
) -> DeescalationReportOut:
    """Computes De-escalation report (T8): hostily spikes, 6-step protocol usage, and anti-patterns."""
    incidents: list[DeescalationIncidentOut] = []

    # Map of 6 de-escalation steps keywords/moves
    step_keywords = {
        "1. Pause & acknowledge emotion": [
            "acknowledge",
            "hear",
            "frustrat",
            "anger",
            "pause",
            "understand your concern",
        ],
        "2. Reformulate statement": [
            "reformulat",
            "paraphras",
            "in other words",
            "if i understand correctly",
            "what you are saying",
        ],
        "3. Capture emotion & set aside": ["set aside", "park", "focus on the matter", "step back"],
        "4. Reframe conversation": ["reframe", "core issue", "shared problem", "mutual objective"],
        "5. Question O/C/O": ["open question", "calibrated question", "how can we", "what would it take", "could we"],
        "6. Discuss options": ["option", "alternative", "proposal", "could consider", "solution"],
    }

    anti_keywords = {
        "Counter-arguing ('I disagree / You are wrong')": [
            "i disagree",
            "you are wrong",
            "that is not true",
            "incorrect",
        ],
        "False understanding ('I understand your situation')": [
            "i understand your situation",
            "i know how you feel",
            "i completely understand",
        ],
        "Premature apologizing": ["i apologize", "we apologize", "i am deeply sorry", "my apologies"],
    }

    prev_hostility = 0
    for i, turn in enumerate(turns):
        turn_num = getattr(turn, "number", 0)
        state_after = getattr(turn, "engine_state_after", {}) or {}
        dials = state_after.get("dials", {}) or {}
        hostility = dials.get("hostility", 0)

        cp_reply = getattr(turn, "reply_text", "") or ""
        # Check if there is a hostility spike (hostility increased or is high >= 45, or negative cue)
        is_spike = (hostility >= 45 and hostility > prev_hostility) or (
            "angry" in cp_reply.lower() or "refuse" in cp_reply.lower()
        )

        if is_spike and i + 1 < len(turns):
            next_turn = turns[i + 1]
            trainee_text = (getattr(next_turn, "trainee_text", None) or "").strip()
            trainee_num = getattr(next_turn, "number", turn_num + 1)
            t_lower = trainee_text.lower()

            next_state = getattr(next_turn, "engine_state_after", {}) or {}
            turn_move_ids: set[str] = set()
            for m in (
                next_state.get("moves") if isinstance(next_state, dict) else getattr(next_state, "moves", [])
            ) or []:
                mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
                if mid:
                    turn_move_ids.add(mid)
            clf = getattr(next_turn, "classification", {}) or {}
            for m in (clf.get("moves") if isinstance(clf, dict) else getattr(clf, "moves", [])) or []:
                mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
                if mid:
                    turn_move_ids.add(mid)

            observed_steps: list[str] = []
            for step_num in range(1, 7):
                step_name = STEP_NAME_BY_NUM[step_num]
                canonical = DE_ESCALATION_STEP_MOVES.get(step_num, set())
                if bool(turn_move_ids & canonical) or any(kw in t_lower for kw in step_keywords.get(step_name, [])):
                    observed_steps.append(step_name)

            observed_antis: list[str] = []
            for anti_name, kw_list in anti_keywords.items():
                if any(kw in t_lower for kw in kw_list):
                    observed_antis.append(anti_name)

            next_state = getattr(next_turn, "engine_state_after", {}) or {}
            # compare the SAME party's hostility: on a multi-party turn `dials` is whoever spoke next,
            # so a greeting to a calm stakeholder would read as de-escalation of the commander's spike
            speaker = state_after.get("active_interlocutor")  # the party whose spike this incident is about
            party_dials = (next_state.get("counterpart_dials") or {}).get(speaker) if speaker else None
            next_dials = party_dials or next_state.get("dials", {}) or {}
            hostility_after = next_dials.get("hostility", hostility)

            if hostility_after < hostility:
                outcome: Literal["de-escalated", "escalated", "neutral"] = "de-escalated"
            elif hostility_after > hostility:
                outcome = "escalated"
            else:
                outcome = "neutral"

            incidents.append(
                DeescalationIncidentOut(
                    turn=turn_num,
                    hostility_level=hostility,
                    trigger=cp_reply[:120] + ("…" if len(cp_reply) > 120 else ""),
                    trainee_turn=trainee_num,
                    trainee_quote=trainee_text[:120] + ("…" if len(trainee_text) > 120 else ""),
                    steps_observed=observed_steps,
                    anti_patterns_observed=observed_antis,
                    hostility_after=hostility_after,
                    outcome=outcome,
                )
            )

        prev_hostility = hostility

    summary = f"Identified {len(incidents)} tension/hostility spike(s) during negotiation."
    deescalated_count = sum(1 for inc in incidents if inc.outcome == "de-escalated")
    if incidents:
        summary += (
            f" Successfully de-escalated {deescalated_count} of {len(incidents)} "
            "tense moments using CCHN active listening."
        )
    else:
        summary += " Dialogue maintained decorum without severe hostility spikes."

    return DeescalationReportOut(
        incidents=incidents,
        summary=summary,
        doc_id="cchn-tool-08",
    )


def compute_prep_vs_reality(
    content: Mapping[str, Any],
    state: State,
    preparation: Mapping[str, Any] | None,
) -> PrepVsRealityOut:
    """Computes Preparation vs Reality: comparing prep modules against actual session occurrences."""
    prep_data = preparation or {}
    has_prep = bool(preparation and any(bool(v) for v in preparation.values()))
    modules: list[PrepVsRealityModuleOut] = []

    # Module 1: Island of Agreements (Facts & Norms)
    island_prep = prep_data.get("island_of_agreements") or {}
    scenario_ioa = content.get("island_of_agreements") or {}
    island_prepared = bool(island_prep and any(island_prep.values()))
    if island_prepared:
        prep_agreed = set(island_prep.get("agreed_facts") or [])
        prep_contested = set(island_prep.get("contested_facts") or [])
        prep_conv_norms = set(island_prep.get("convergent_norms") or [])
        author_contested = set(scenario_ioa.get("contested_facts") or [])
        misplaced = len(prep_agreed & author_contested)
        planned = (
            f"Categorized {len(prep_agreed)} agreed facts, {len(prep_contested)} contested facts, "
            f"and {len(prep_conv_norms)} convergent norms."
        )
        alignment: Literal["aligned", "diverged", "untested", "skipped"] = "diverged" if misplaced > 0 else "aligned"
    else:
        planned = None
        alignment = "skipped"
    reality = f"Session explored agreements; covered {len(state.covered_details)} operational checklist items."
    modules.append(
        PrepVsRealityModuleOut(
            module_id="island_of_agreements",
            label="Island of Agreements (Facts & Norms)",
            prepared=island_prepared,
            planned=planned,
            reality=reality,
            alignment=alignment,
            insight=(
                "Opening on uncontested facts and convergent norms builds trust before addressing sensitive points."
            ),
        )
    )

    # Module 2: Counterpart Iceberg
    cp = (content.get("counterparts") or [{}])[0]
    cp_iceberg_prep = prep_data.get("counterpart_iceberg") or {}
    cp_prepared = bool(cp_iceberg_prep and any(cp_iceberg_prep.values()))
    if cp_prepared:
        pos = str(cp_iceberg_prep.get("position") or "")
        reasoning = str(cp_iceberg_prep.get("tactical_reasoning") or "")
        values = str(cp_iceberg_prep.get("motives_values") or "")
        parts = []
        if pos:
            parts.append(f"Position: '{pos[:30]}…'")
        if reasoning:
            parts.append(f"Reasoning: '{reasoning[:30]}…'")
        if values:
            parts.append(f"Values: '{values[:30]}…'")
        planned = f"Hypothesized {', '.join(parts)}." if parts else "Formulated counterpart iceberg hypotheses."
        alignment = "aligned" if len(state.revealed) > 0 else "untested"
    else:
        planned = None
        alignment = "skipped"
    modules.append(
        PrepVsRealityModuleOut(
            module_id="counterpart_iceberg",
            label="Counterpart Iceberg Analysis",
            prepared=cp_prepared,
            planned=planned,
            reality=f"Revealed {len(state.revealed)} hidden interests during negotiation.",
            alignment=alignment,
            insight="Anticipating tactical reasoning prevents surprises when counterpart presents logistical barriers.",
        )
    )

    # Module 3: Level & Narrative
    level_prep = prep_data.get("level_and_narrative") or {}
    lvl_prepared = bool(level_prep and any(level_prep.values()))
    if lvl_prepared:
        exp_lvl = str(level_prep.get("expected_level") or "technical")
        narrative_why = str(level_prep.get("why") or "")
        planned = f"Planned starting level '{exp_lvl}'" + (
            f" (Narrative: {narrative_why[:40]}…)" if narrative_why else "."
        )
        alignment = "aligned" if exp_lvl.lower() == state.level.lower() else "diverged"
    else:
        planned = None
        alignment = "skipped"
    modules.append(
        PrepVsRealityModuleOut(
            module_id="level_and_narrative",
            label="Typology & Narrative",
            prepared=lvl_prepared,
            planned=planned,
            reality=f"Dialogue operated at the {state.level} level.",
            alignment=alignment,
            insight="Anchoring the dialogue at the professional/technical level avoids early political friction.",
        )
    )

    # Module 4: Lines & Options
    lines_prep = prep_data.get("lines_and_options") or {}
    lines_prepared = bool(lines_prep and any(lines_prep.values()))
    deal_result = state.outcome.result if state.outcome else "no agreement"
    if lines_prepared:
        ideal = str(lines_prep.get("ideal_outcome") or "ideal")
        bottom = str(lines_prep.get("bottom_line") or "bottom line")
        planned = f"Mapped ideal A ('{ideal[:30]}…'), bottom line B ('{bottom[:30]}…'), and red line C."
        if state.outcome and state.outcome.result == "success":
            alignment = "aligned"
        elif state.outcome and state.outcome.id == "red_line":
            alignment = "diverged"
        else:
            alignment = "untested"
    else:
        planned = None
        alignment = "skipped"
    modules.append(
        PrepVsRealityModuleOut(
            module_id="lines_and_options",
            label="Lines & Options (A-B-C Scale)",
            prepared=lines_prepared,
            planned=planned,
            reality=f"Concluded with {deal_result} outcome.",
            alignment=alignment,
            insight="Knowing the bottom line beforehand prevents unauthorized commitments under pressure.",
        )
    )

    # Module 5: Information Quality (Claims Assessment)
    info_prep = prep_data.get("information_quality") or {}
    claims = content.get("claims") or []
    info_prepared = bool(info_prep and info_prep.get("claims_assessment"))
    if info_prepared:
        assessed = info_prep.get("claims_assessment") or {}
        planned = f"Assessed {len(assessed)} of {len(claims)} operational claims for source credibility."
        alignment = "aligned" if len(assessed) >= max(1, len(claims) // 2) else "diverged"
    else:
        planned = None
        alignment = "skipped"
    modules.append(
        PrepVsRealityModuleOut(
            module_id="information_quality",
            label="Information Quality & Claims",
            prepared=info_prepared,
            planned=planned,
            reality=f"Encounter referenced {len(claims)} context claims from local sources.",
            alignment=alignment,
            insight="Evaluating information quality upfront prevents negotiating under false factual assumptions.",
        )
    )

    # Module 6: Legitimacy Profile
    legit_prep = prep_data.get("legitimacy_profile") or {}
    author_legit = cp.get("legitimacy_weights") or {}
    emphasis = legit_prep.get("emphasis") or []
    legit_prepared = bool(legit_prep and emphasis)
    top_sources = [k for k, v in author_legit.items() if isinstance(v, (int, float)) and v >= 60]
    if legit_prepared:
        matched = [s for s in emphasis if s in top_sources]
        planned = f"Prioritized legitimacy sources: {', '.join(emphasis)}."
        alignment = "aligned" if matched or not top_sources else "diverged"
    else:
        planned = None
        alignment = "skipped"
    modules.append(
        PrepVsRealityModuleOut(
            module_id="legitimacy_profile",
            label="Legitimacy Profile",
            prepared=legit_prepared,
            planned=planned,
            reality=f"Counterpart values: {', '.join(top_sources) if top_sources else 'legal and moral'} authority.",
            alignment=alignment,
            insight=(
                "Appealing to the counterpart's own source of legitimacy reduces resistance to humanitarian requests."
            ),
        )
    )

    # Module 7: Common Shared Space (CSS)
    css_prep = prep_data.get("common_shared_space") or {}
    conv = css_prep.get("convergent") or []
    div = css_prep.get("divergent") or []
    css_prepared = bool(css_prep and (conv or div))
    conv_norms = scenario_ioa.get("convergent_norms") or []
    if css_prepared:
        planned = f"Mapped {len(conv)} shared priorities and {len(div)} divergent boundaries in Common Shared Space."
        alignment = "aligned" if len(conv) > 0 else "untested"
    else:
        planned = None
        alignment = "skipped"
    modules.append(
        PrepVsRealityModuleOut(
            module_id="common_shared_space",
            label="Common Shared Space (CSS)",
            prepared=css_prepared,
            planned=planned,
            reality=f"Context identified {len(conv_norms)} convergent normative anchors.",
            alignment=alignment,
            insight=(
                "Grounding proposals in the common shared space transforms bilateral demands into "
                "shared responsibilities."
            ),
        )
    )

    # Module 8: Network Influence
    net_prep = prep_data.get("network") or {}
    stakeholders = content.get("stakeholders") or []
    supp = net_prep.get("supportive") or []
    opp = net_prep.get("opposed") or []
    net_prepared = bool(net_prep and (supp or opp))
    eng_count = sum(state.stakeholder_engagements.values())
    if net_prepared:
        planned = f"Anticipated network: {len(supp)} supportive and {len(opp)} opposed stakeholders."
        alignment = "aligned" if eng_count > 0 or not stakeholders else "untested"
    else:
        planned = None
        alignment = "skipped"
    modules.append(
        PrepVsRealityModuleOut(
            module_id="network",
            label="Stakeholder Network Influence",
            prepared=net_prepared,
            planned=planned,
            reality=(
                f"Engaged {len(state.stakeholder_engagements)} external stakeholders ({eng_count} total interactions)."
            ),
            alignment=alignment,
            insight=(
                "Mobilizing third-party influencers reshapes the negotiation environment when direct dialogue stalls."
            ),
        )
    )

    # Module 9: Meeting Checklist
    check_prep = prep_data.get("meeting_checklist") or {}
    notes = str(check_prep.get("notes") or "").strip()
    check_prepared = bool(check_prep and notes)
    if check_prepared:
        planned = f"Documented meeting checklist ({len(notes.splitlines())} operational items)."
        alignment = "aligned"
    else:
        planned = None
        alignment = "skipped"
    modules.append(
        PrepVsRealityModuleOut(
            module_id="meeting_checklist",
            label="Meeting Checklist & Arrangements",
            prepared=check_prepared,
            planned=planned,
            reality=f"Session progressed through {state.turn} turns with {len(state.covered_details)} details covered.",
            alignment=alignment,
            insight="Preparation on meeting format, security perimeter, and team roles prevents operational confusion.",
        )
    )

    summary = "Preparation sheet compared with simulation execution."
    if has_prep:
        summary += " Pre-negotiation grid provided tactical clarity during the exchange."
    else:
        summary += " Preparation was skipped. Using the Naivasha Grid prior to negotiation improves predictability."

    return PrepVsRealityOut(
        has_preparation=has_prep,
        modules=modules,
        summary=summary,
        doc_id="cchn-naivasha-grid",
    )


def compute_reflection_section(
    reflection: Mapping[str, Any] | None,
    content: Mapping[str, Any] | None = None,
) -> ReflectionSectionOut:
    """Builds debrief reflection questions and answers, using scenario questions if defined or CCHN defaults."""
    if not reflection:
        answers: Mapping[str, Any] = {}
    elif "answers" in reflection and isinstance(reflection["answers"], (dict, Mapping)):
        answers = reflection["answers"]
    else:
        answers = reflection

    custom_questions = (content.get("reflection") or {}).get("questions") if content else None
    if custom_questions and isinstance(custom_questions, list):
        questions = []
        for q in custom_questions:
            if isinstance(q, dict) and "id" in q and "prompt" in q:
                qid = str(q["id"])
                ans = str(answers[qid]) if answers.get(qid) is not None else None
                questions.append(
                    ReflectionQuestionOut(
                        id=qid,
                        prompt=str(q["prompt"]),
                        guidance=str(q.get("guidance") or ""),
                        answer=ans,
                    )
                )
    else:
        q1_answer = str(answers["t6_counterpart_perspective"]) if answers.get("t6_counterpart_perspective") else None
        q2_answer = str(answers["t6_options_under_resistance"]) if answers.get("t6_options_under_resistance") else None
        q3_answer = str(answers["t6_clear_next_steps"]) if answers.get("t6_clear_next_steps") else None

        questions = [
            ReflectionQuestionOut(
                id="t6_counterpart_perspective",
                prompt=(
                    "Were you available to explore and discuss the counterpart's points on "
                    "their own terms before presenting your own demands?"
                ),
                guidance=(
                    "In CCHN doctrine (Tool 6), active perceiving precedes active persuading. "
                    "Did you validate their operational constraints before advocating your needs?"
                ),
                answer=q1_answer,
            ),
            ReflectionQuestionOut(
                id="t6_options_under_resistance",
                prompt=(
                    "Were you able to raise creative options and alternatives when confronted "
                    "with resistance, rather than insisting on a single solution?"
                ),
                guidance=(
                    "When reaching an impasse on terms, bringing up multiple options expands "
                    "the Common Shared Space and avoids positional deadlock."
                ),
                answer=q2_answer,
            ),
            ReflectionQuestionOut(
                id="t6_clear_next_steps",
                prompt=(
                    "Did you conclude with clear, reciprocal next steps and a shared understanding "
                    "of what to do if views diverge during implementation?"
                ),
                guidance=(
                    "CCHN Tool 7 emphasizes that every meeting should formulate next steps and an "
                    "escalation-prevention process ('negotiator's hotline') for field hiccups."
                ),
                answer=q3_answer,
            ),
        ]

    completed = len(questions) > 0 and all(bool(q.answer and q.answer.strip()) for q in questions)

    return ReflectionSectionOut(
        questions=questions,
        completed=completed,
        doc_id="cchn-tool-06",
    )


def compute_competences(
    content: Mapping[str, Any],
    turns: Sequence[Any],
    session_debrief: Mapping[str, Any] | None,
) -> CompetencesSectionOut:
    """Maps rubric dimensions to CCHN Competence Chart (Core, Advanced, Expert)."""
    # Extract last scored turn's evaluations if available
    scored_turns = [t for t in turns if getattr(t, "scores", None)]
    latest_scores = getattr(scored_turns[-1], "scores", {}) if scored_turns else {}
    score_dict: dict[str, int | None] = {}
    quote_dict: dict[str, str | None] = {}

    for item in latest_scores.get("scores") or []:
        if isinstance(item, dict):
            dim_id = item.get("id", "")
            score_dict[dim_id] = item.get("score")
            quote_dict[dim_id] = item.get("quote")

    rubric_dims = (content.get("rubric") or {}).get("dimensions") or []

    # Mapping dimensions into Core, Advanced, Expert
    core_keys = {
        "context_analysis",
        "identifies_interest",
        "asks_good_question",
        "humanitarian_principles",
        "red_lines",
        "emotional_intelligence",
        "de_escalation",
        "active_listening",
    }
    advanced_keys = {
        "options_generation",
        "creative_options",
        "offers_options",
        "compromise_balance",
        "identifies_compromise",
        "adaptability",
        "level_navigation",
        "stakeholder_influence",
    }
    expert_keys = {"mandate_integrity", "refers_to_mandator", "strategic_forecasting", "leadership_mentoring"}

    core_dims: list[CompetenceDimensionOut] = []
    adv_dims: list[CompetenceDimensionOut] = []
    exp_dims: list[CompetenceDimensionOut] = []

    for dim in rubric_dims:
        label = dim.replace("_", " ").title()
        dim_score = score_dict.get(dim)
        dim_quote = quote_dict.get(dim)
        obj = CompetenceDimensionOut(id=dim, label=label, score=dim_score, quote=dim_quote)

        if dim in core_keys:
            core_dims.append(obj)
        elif dim in advanced_keys:
            adv_dims.append(obj)
        elif dim in expert_keys:
            exp_dims.append(obj)
        else:
            # Fallback based on naming heuristic
            if any(k in dim for k in ("listen", "emotion", "question", "interest", "context")):
                core_dims.append(obj)
            elif any(k in dim for k in ("option", "compromise", "adapt", "trade")):
                adv_dims.append(obj)
            else:
                core_dims.append(obj)

    # Ensure each tier has at least a representative anchor if scenario didn't specify
    if not core_dims:
        core_dims.append(
            CompetenceDimensionOut(
                id="interest_analysis", label="Capacity to analyze contexts & interests", score=4, quote=None
            )
        )
    if not adv_dims:
        adv_dims.append(
            CompetenceDimensionOut(
                id="options_creation", label="Ability to create options out of complex problems", score=3, quote=None
            )
        )
    if not exp_dims:
        exp_dims.append(
            CompetenceDimensionOut(
                id="mandate_alignment",
                label="Ability to align priorities and maintain clear mandate",
                score=4,
                quote=None,
            )
        )

    tiers = [
        CompetenceTierOut(
            tier="core",
            label="Core Competences",
            dimensions=core_dims,
            summary=(
                "Basic frontline requirements: context analysis, active listening, "
                "dealing with difficult interlocutors, and emotional intelligence."
            ),
        ),
        CompetenceTierOut(
            tier="advanced",
            label="Advanced Competences",
            dimensions=adv_dims,
            summary=(
                "Complex frontline negotiation: creating options, balancing interests and "
                "compromises, and environmental adaptability."
            ),
        ),
        CompetenceTierOut(
            tier="expert",
            label="Expert Competences",
            dimensions=exp_dims,
            summary=(
                "Strategic leadership: aligning priorities within the organization, "
                "strict mandate adherence, and mentoring."
            ),
        ),
    ]

    return CompetencesSectionOut(
        tiers=tiers,
        doc_id="cchn-competences",
    )


def compute_cchn_debrief(
    content: Mapping[str, Any],
    state: State,
    turns: Sequence[Any],
    preparation: Mapping[str, Any] | None,
    reflection: Mapping[str, Any] | None,
    session_debrief: Mapping[str, Any] | None,
) -> CchnDebriefOut:
    """Master evaluator assembling CCHN debrief modules, filtered by debrief.sections if specified."""
    debrief_cfg = content.get("debrief") or {}
    sections_filter = debrief_cfg.get("sections")
    allowed = set(sections_filter) if isinstance(sections_filter, list) else None

    def wanted(sec_id: str) -> bool:
        return allowed is None or sec_id in allowed

    agreement = compute_agreement_check(content, state, turns) if wanted("agreement_check") else None
    zones = compute_zones(content, state) if wanted("zones") else None
    level_timeline = compute_level_timeline(content, state, turns) if wanted("level_timeline") else None
    iceberg = compute_iceberg_depth(content, state, preparation) if wanted("iceberg_depth") else None
    deescalation = compute_deescalation_report(turns) if wanted("deescalation_report") else None
    prep_reality = compute_prep_vs_reality(content, state, preparation) if wanted("prep_vs_reality") else None
    reflection_out = compute_reflection_section(reflection, content) if wanted("reflection") else None
    competences_out = compute_competences(content, turns, session_debrief) if wanted("competences") else None

    knowledge_links = []
    if agreement is not None:
        knowledge_links.append(DOCTRINE_LINKS["cchn-tool-07"])
    if zones is not None:
        knowledge_links.append(DOCTRINE_LINKS["cchn-tool-13"])
    if level_timeline is not None:
        knowledge_links.append(DOCTRINE_LINKS["cchn-tool-04"])
    if iceberg is not None:
        knowledge_links.append(DOCTRINE_LINKS["cchn-tool-09"])
    if deescalation is not None:
        knowledge_links.append(DOCTRINE_LINKS["cchn-tool-08"])
    if prep_reality is not None:
        knowledge_links.append(DOCTRINE_LINKS["cchn-naivasha-grid"])
    if reflection_out is not None:
        knowledge_links.append(DOCTRINE_LINKS["cchn-tool-06"])
    if competences_out is not None:
        knowledge_links.append(DOCTRINE_LINKS["cchn-competences"])

    return CchnDebriefOut(
        agreement_check=agreement,
        zones=zones,
        level_timeline=level_timeline,
        iceberg_depth=iceberg,
        deescalation_report=deescalation,
        prep_vs_reality=prep_reality,
        reflection=reflection_out,
        competences=competences_out,
        knowledge_links=knowledge_links,
    )
