import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { S } from "../../api/client";
import { CchnDebriefSection } from "./CchnDebriefSection";

// Mock api call
vi.mock("../../api/client", async () => {
  const actual = await vi.importActual("../../api/client");
  return {
    ...actual,
    api: vi.fn().mockResolvedValue({}),
  };
});

const MOCK_CCHN_DEBRIEF: S["CchnDebriefOut"] = {
  agreement_check: {
    doc_id: "cchn-tool-07",
    is_deal: true,
    overall_score: 8,
    terms_sheet: [
      "Access granted for humanitarian medical convoy.",
      "Checkpoint passage without armed escort.",
    ],
    criteria: [
      {
        id: "clear_language",
        label: "Clear & Unambiguous Language",
        score: 2,
        status: "met",
        finding: "All operational details are explicitly specified without vague terms.",
        evidence: "The convoy will pass at 08:00 without delay.",
      },
      {
        id: "roles_and_tasks",
        label: "Defined Roles & Tasks",
        score: 2,
        status: "met",
        finding: "Both team leader and checkpoint commander responsibilities are outlined.",
        evidence: null,
      },
    ],
  },
  zones: {
    doc_id: "cchn-tool-13",
    zone: "F",
    zone_label: "Optimal Agreement",
    description: "The concluded agreement is within both parties' acceptable negotiation zones.",
    scale: {
      trainee: {
        ideal_outcome: "Unimpeded medical convoy passage",
        bottom_line: "Inspection of vehicle exterior only",
        red_line: "Armed escort or surrender of medical kits",
      },
      counterpart: {
        ideal_outcome: "Full search and armed convoy escort",
        bottom_line: "Cargo manifest verification",
        red_line: "Unregulated cross-line transit",
      },
    },
    tier_3_parked: true,
    tier_3_issues: [
      {
        id: "political_legitimacy",
        label: "Recognition of de-facto authorities",
        status: "parked",
        finding: "Sensitive political sovereignty discussion was deliberately kept outside the corridor deal.",
      },
    ],
  },
  level_timeline: {
    doc_id: "cchn-tool-04",
    start_level: "technical",
    final_level: "technical",
    summary: "Discussion stayed largely anchored in technical modalities.",
    entries: [
      {
        turn: 1,
        speaker: "counterpart",
        level: "political",
        direction: "politicize",
        shifted: true,
        matched: false,
        note: "Counterpart questioned organizational neutrality.",
      },
      {
        turn: 2,
        speaker: "trainee",
        level: "technical",
        direction: "depoliticize",
        shifted: true,
        matched: true,
        note: "Trainee successfully reframed discussion back to medical patient needs.",
      },
    ],
  },
  iceberg_depth: {
    doc_id: "cchn-tool-09",
    max_layer_reached: "reasoning",
    summary: "Trainee uncovered the commander's tactical reasoning regarding local security orders.",
    layers: [
      {
        layer: "position",
        label: "Stated Position",
        reached: true,
        counterpart_content: ["No passage allowed without high-level clearance."],
        prep_guess: "Counterpart will block access citing safety.",
        accuracy_note: "Matches pre-negotiation hypothesis.",
      },
      {
        layer: "reasoning",
        label: "Tactical Reasoning",
        reached: true,
        counterpart_content: ["Fears reprimand from central command for perimeter breaches."],
        prep_guess: "Needs liability protection from command.",
        accuracy_note: "Identified underlying fear of disciplinary action.",
      },
      {
        layer: "motives_values",
        label: "Deep Motives & Values",
        reached: false,
        counterpart_content: [],
        prep_guess: null,
        accuracy_note: "Conversation concluded before reaching core worldview.",
      },
    ],
  },
  deescalation_report: {
    doc_id: "cchn-tool-08",
    summary: "One tension spike was managed with active listening and tactical pauses.",
    incidents: [
      {
        turn: 3,
        trigger: "Counterpart raised voice regarding previous unauthorized crossings.",
        hostility_level: 4,
        hostility_after: 2,
        trainee_turn: 3,
        trainee_quote: "I understand your security concerns and we take perimeter protocols seriously.",
        steps_observed: ["Active listening", "De-centering / Acknowledgment", "Reframing"],
        anti_patterns_observed: [],
        outcome: "de-escalated",
      },
    ],
  },
  prep_vs_reality: {
    doc_id: "cchn-naivasha-grid",
    has_preparation: true,
    summary: "Strong correlation between anticipated bottom lines and counterpart constraints.",
    modules: [
      {
        module_id: "island_of_agreements",
        label: "Island of Agreements",
        prepared: true,
        planned: "Agreed on emergency health urgency; contested on inspection protocol.",
        reality: "Inspection protocol was resolved through third-party seal checks.",
        alignment: "aligned",
        insight: "Anchoring on convergent norms prevented early deadlock.",
      },
    ],
  },
  reflection: {
    doc_id: "cchn-tool-06",
    completed: false,
    questions: [
      {
        id: "q1_strengths",
        prompt: "What went well in applying CCHN tools during this transaction?",
        guidance: "Strengths",
        answer: "",
      },
      {
        id: "q2_divergence",
        prompt: "Where did reality diverge most sharply from your preparation?",
        guidance: "Surprises",
        answer: "",
      },
      {
        id: "q3_adjustments",
        prompt: "What will you adjust in your negotiation approach for next time?",
        guidance: "Adjustments",
        answer: "",
      },
    ],
  },
  competences: {
    doc_id: "cchn-competences",
    tiers: [
      {
        tier: "core",
        label: "Foundational Humanitarian Negotiation",
        summary: "Demonstrated strong empathy, role boundaries, and procedural respect.",
        dimensions: [
          { id: "active_listening", label: "Active Listening", score: 4 },
          { id: "neutrality", label: "Neutrality & Independence", score: 5 },
        ],
      },
    ],
  },
  knowledge_links: [
    {
      id: "cchn-tool-07",
      title: "Tool 7: Drafting an Agreement",
      framework: "CCHN Field Manual",
      citation: "Module 4, Section 7",
      summary: "Guidelines on turning consensus into actionable, unambiguous operational terms.",
      tags: ["agreements", "terms-sheet", "closure"],
    },
  ],
};

describe("CchnDebriefSection", () => {
  it("renders header, badges, and all 5 tabs", () => {
    render(<CchnDebriefSection sessionId="sess-123" cchnDebrief={MOCK_CCHN_DEBRIEF} />);

    expect(screen.getByText(/CCHN Field Doctrine Analysis/i)).toBeInTheDocument();
    expect(screen.getByText("CCHN Strategic Reflection")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: /Agreement & Zones/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Levels, Iceberg & Hostility/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Prep vs Reality/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Self-Reflection/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Competences & Doctrine/i })).toBeInTheDocument();
  });

  it("renders Agreement Check terms sheet and criteria on default tab", () => {
    render(<CchnDebriefSection sessionId="sess-123" cchnDebrief={MOCK_CCHN_DEBRIEF} />);

    expect(screen.getByText(/Agreement Concluded/i)).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("Access granted for humanitarian medical convoy.")).toBeInTheDocument();
    expect(screen.getByText("Clear & Unambiguous Language")).toBeInTheDocument();
    expect(screen.getByText("Zone F: Optimal Agreement")).toBeInTheDocument();
    expect(screen.getByText("Recognition of de-facto authorities")).toBeInTheDocument();
  });

  it("switches to Dynamics tab and displays Level Timeline, Iceberg layers, and De-escalation report", () => {
    render(<CchnDebriefSection sessionId="sess-123" cchnDebrief={MOCK_CCHN_DEBRIEF} />);

    fireEvent.click(screen.getByRole("button", { name: /Levels, Iceberg & Hostility/i }));

    expect(screen.getByText("Conversation Level Movements")).toBeInTheDocument();
    expect(screen.getByText("Trainee successfully reframed discussion back to medical patient needs.")).toBeInTheDocument();
    expect(screen.getByText("3-Layer Iceberg Depth Reached")).toBeInTheDocument();
    expect(screen.getByText("Layer 2: Tactical Reasoning")).toBeInTheDocument();
    expect(screen.getByText(/Fears reprimand from central command/i)).toBeInTheDocument();
    expect(screen.getByText("Hostility Management & 6-Step Protocol")).toBeInTheDocument();
    expect(screen.getByText(/I understand your security concerns/i)).toBeInTheDocument();
  });

  it("switches to Prep vs Reality tab and displays comparison module", () => {
    render(<CchnDebriefSection sessionId="sess-123" cchnDebrief={MOCK_CCHN_DEBRIEF} />);

    fireEvent.click(screen.getByRole("button", { name: /Prep vs Reality/i }));

    expect(screen.getByText("Hypotheses vs Operational Reality")).toBeInTheDocument();
    expect(screen.getByText("Island of Agreements")).toBeInTheDocument();
    expect(screen.getByText("Anchoring on convergent norms prevented early deadlock.")).toBeInTheDocument();
  });

  it("switches to Reflection tab, fills answers and saves reflection", async () => {
    const onSaved = vi.fn();
    render(
      <CchnDebriefSection
        sessionId="sess-123"
        cchnDebrief={MOCK_CCHN_DEBRIEF}
        onReflectionSaved={onSaved}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Self-Reflection/i }));

    expect(screen.getByText("Transaction Reflection Checklist")).toBeInTheDocument();
    const textarea = screen.getByLabelText(/What went well in applying CCHN tools during this transaction\?/i);
    fireEvent.change(textarea, { target: { value: "Reframing back to patient needs kept the dialogue constructive." } });

    const submitBtn = screen.getByRole("button", { name: /Save Reflection & Sync with Coach/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Reflection saved and synced with your AI Coach!/i)).toBeInTheDocument();
    });
    expect(onSaved).toHaveBeenCalledWith(
      expect.objectContaining({
        q1_strengths: "Reframing back to patient needs kept the dialogue constructive.",
      })
    );
  });

  it("switches to Competences tab and displays tiers and doctrine references", () => {
    render(<CchnDebriefSection sessionId="sess-123" cchnDebrief={MOCK_CCHN_DEBRIEF} />);

    fireEvent.click(screen.getByRole("button", { name: /Competences & Doctrine/i }));

    expect(screen.getByText("Foundational Humanitarian Negotiation")).toBeInTheDocument();
    expect(screen.getByText(/Active Listening \(4\/5\)/i)).toBeInTheDocument();
    expect(screen.getByText("Tool 7: Drafting an Agreement")).toBeInTheDocument();
  });
});
